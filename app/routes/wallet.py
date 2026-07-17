"""Wallet routes — balance, fund, transactions."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.wallet_service import get_wallet, get_wallet_transactions
from app.services.payment_service import initialize_payment, verify_payment
from app.db import get_db
from app.messages import MSG
import uuid

wallet_bp = Blueprint("wallet", __name__)


@wallet_bp.route("", methods=["GET"])
@require_auth
def get_balance():
    """
    Get wallet balance and virtual account info.
    ---
    tags: [Wallet]
    responses:
      200:
        description: Wallet details
    """
    wallet = get_wallet(g.user_id)
    if not wallet:
        return jsonify({"error": MSG.WALLET_NOT_FOUND}), 404

    db = get_db()
    virtual_account = None
    try:
        va_rows = (
            db.table("virtual_accounts")
            .select("account_number,bank_name,account_name,provider_reference")
            .eq("user_id", g.user_id)
            .limit(1)
            .execute()
        )
        virtual_account = va_rows[0] if va_rows else None
    except Exception:
        pass

    return jsonify({
        "balance": float(wallet.get("balance", 0)),
        "currency": wallet.get("currency", "NGN"),
        "virtual_account": virtual_account,
    }), 200


@wallet_bp.route("/fund/card", methods=["POST"])
@require_auth
def fund_via_card():
    """
    Initialize a card payment to top up wallet.
    ---
    tags: [Wallet]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [amount]
          properties:
            amount: {type: number, description: "Amount in Naira"}
            callback_url: {type: string}
    responses:
      200:
        description: Paystack authorization_url returned
    """
    data = request.get_json(force=True)
    from flask import current_app
    amount = float(data.get("amount", 0))
    min_topup = current_app.config.get("WALLET_MIN_CARD_TOPUP", 100)
    if amount < min_topup:
        return jsonify({"error": MSG.WALLET_MIN_TOPUP.format(min=min_topup)}), 400

    db = get_db()
    auth_user_rows = db.table("profiles").select("id").eq("id", g.user_id).single().execute()
    if not auth_user_rows:
        return jsonify({"error": MSG.WALLET_USER_NOT_FOUND}), 404

    ref_prefix = current_app.config.get("WALLET_REF_PREFIX", "HG-WALLET-")
    reference = f"{ref_prefix}{str(uuid.uuid4())[:8].upper()}"

    from flask import current_app as _cur_app
    if not _cur_app.config.get("PAYSTACK_SECRET_KEY"):
        return jsonify({"error": "Card payments are not configured on this server."}), 502

    try:
        email = g.jwt_payload.get("email", "")
        result = initialize_payment(
            email=email,
            amount_naira=amount,
            reference=reference,
            metadata={"user_id": g.user_id, "type": "wallet_topup"},
            callback_url=data.get("callback_url"),
        )
        return jsonify({
            "authorization_url": result["authorization_url"],
            "access_code": result["access_code"],
            "reference": reference,
        }), 200
    except ValueError as e:
        # Payment gateway rejected the request (bad key, validation error, etc.)
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        _cur_app.logger.error("wallet fund/card error: %s", e)
        return jsonify({"error": "Payment gateway unavailable. Please try again later."}), 502


@wallet_bp.route("/fund/bank", methods=["POST"])
@require_auth
def request_virtual_account():
    """
    Provision a Paystack Dedicated Virtual Account for bank transfers.
    Idempotent — returns existing account if one already exists.
    ---
    tags: [Wallet]
    responses:
      200:
        description: Virtual account details
      201:
        description: New virtual account created
      502:
        description: Paystack error creating account
    """
    db = get_db()

    try:
        existing = (
            db.table("virtual_accounts")
            .select("account_number,bank_name,account_name,provider_reference")
            .eq("user_id", g.user_id)
            .limit(1)
            .execute()
        )
        if existing:
            return jsonify({"virtual_account": existing[0], "created": False}), 200
    except Exception:
        existing = None

    try:
        profile = (
            db.table("profiles")
            .select("email,full_name,phone")
            .eq("id", g.user_id)
            .single()
            .execute()
        )
    except Exception:
        profile = None
    if not profile:
        return jsonify({"error": MSG.WALLET_PROFILE_NOT_FOUND}), 404

    email = profile.get("email") or g.jwt_payload.get("email", "")
    from app.services.payment_service import create_virtual_account
    try:
        account = create_virtual_account(
            user_id=g.user_id,
            email=email,
            full_name=profile.get("full_name") or "HG User",
            phone=profile.get("phone"),
        )
    except Exception as exc:
        err_str = str(exc)
        # In sandbox/development, Paystack dedicated NUBAN requires a live API key.
        # Set PAYSTACK_SANDBOX_MOCK_NUBAN=true to receive a mock response for UI testing.
        from flask import current_app as _app
        if _app.config.get("PAYSTACK_SANDBOX_MOCK_NUBAN"):
            mock_account = {
                "account_number": "0000000000",
                "bank_name": "Test Bank (Sandbox Mock)",
                "account_name": profile.get("full_name") or "HG User",
                "provider_reference": "mock-nuban-sandbox",
            }
            return jsonify({"virtual_account": mock_account, "created": True, "mock": True}), 201
        return jsonify({
            "error": MSG.WALLET_VA_FAILED.format(error=err_str),
            "sandbox_info": (
                "Paystack dedicated NUBAN is not available on sandbox/test keys. "
                "Set PAYSTACK_SANDBOX_MOCK_NUBAN=true in your environment to enable "
                "a mock virtual account for development."
            ),
        }), 400

    try:
        db.table("virtual_accounts").insert({
            "user_id": g.user_id,
            "account_number": account["account_number"],
            "bank_name": account["bank_name"],
            "account_name": account["account_name"],
            "provider_reference": str(account.get("reference", "")),
            "provider": "paystack",
        })
    except Exception:
        pass

    return jsonify({"virtual_account": account, "created": True}), 201



@wallet_bp.route("/admin/transactions", methods=["GET"])
@require_role("admin")
def admin_wallet_transactions():
    """
    List wallet transactions across all users (admin only).
    ---
    tags: [Wallet]
    parameters:
      - in: query
        name: user_id
        type: string
        description: Filter by user UUID
      - in: query
        name: type
        type: string
        description: Filter by reference_type (topup, order_payment, refund, withdrawal, bank_transfer)
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Wallet transactions across all users
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("wallet_transactions").select("*,profiles!user_id(full_name,email)")
    uid = request.args.get("user_id")
    if uid:
        q = q.eq("user_id", uid)
    tx_type = request.args.get("type")
    if tx_type:
        q = q.eq("reference_type", tx_type)
    from_date = request.args.get("from_date")
    if from_date:
        q = q.gte("created_at", from_date)
    to_date = request.args.get("to_date")
    if to_date:
        q = q.lte("created_at", to_date + "T23:59:59Z")
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"transactions": rows, "count": len(rows)}), 200


@wallet_bp.route("/transactions", methods=["GET"])
@require_auth
def wallet_transactions():
    """
    Get wallet transaction history. Filter by type: topup, order_payment, refund, withdrawal, bank_transfer.
    ---
    tags: [Wallet]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: type
        type: string
        description: Filter by reference_type (topup, order_payment, refund, withdrawal, bank_transfer)
    responses:
      200:
        description: Wallet transaction history
    """
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    tx_type = request.args.get("type") or None
    txns = get_wallet_transactions(g.user_id, limit=limit, offset=offset, tx_type=tx_type)
    return jsonify(txns), 200
