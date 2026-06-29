"""Wallet routes — balance, fund, transactions."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.wallet_service import get_wallet, get_wallet_transactions
from app.services.payment_service import initialize_payment, verify_payment
from app.db import get_db
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
        return jsonify({"error": "Wallet not found"}), 404

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
        return jsonify({"error": f"Minimum top-up is ₦{min_topup:.0f}"}), 400

    db = get_db()
    auth_user_rows = db.table("profiles").select("id").eq("id", g.user_id).single().execute()
    if not auth_user_rows:
        return jsonify({"error": "User not found"}), 404

    reference = f"HG-WALLET-{str(uuid.uuid4())[:8].upper()}"

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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": "Profile not found"}), 404

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
        return jsonify({"error": f"Could not provision virtual account: {exc}"}), 502

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


@wallet_bp.route("/withdraw", methods=["POST"])
@require_auth
def request_withdrawal():
    """
    Request a wallet withdrawal to a bank account.
    Creates a pending withdrawal record for admin review and processing.
    ---
    tags: [Wallet]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [amount, bank_code, account_number, account_name]
          properties:
            amount: {type: number, description: "Amount in Naira to withdraw"}
            bank_code: {type: string, description: "Paystack bank code"}
            account_number: {type: string}
            account_name: {type: string}
            narration: {type: string}
    responses:
      201:
        description: Withdrawal request submitted
      400:
        description: Insufficient balance or validation error
    """
    data = request.get_json(force=True)
    for f in ["amount", "bank_code", "account_number", "account_name"]:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    from flask import current_app
    amount = float(data["amount"])
    min_withdrawal = current_app.config.get("WALLET_MIN_WITHDRAWAL", 500)
    if amount < min_withdrawal:
        return jsonify({"error": f"Minimum withdrawal is ₦{min_withdrawal:.0f}"}), 400

    db = get_db()
    wallet = get_wallet(g.user_id)
    if not wallet:
        return jsonify({"error": "Wallet not found"}), 404

    balance = float(wallet.get("balance", 0))
    if balance < amount:
        return jsonify({"error": f"Insufficient balance. Available: ₦{balance:.2f}"}), 400

    from datetime import datetime, timezone
    import uuid as _uuid
    reference = f"HG-WD-{_uuid.uuid4().hex[:8].upper()}"

    record = {
        "user_id": g.user_id,
        "amount": amount,
        "bank_code": data["bank_code"],
        "account_number": data["account_number"],
        "account_name": data["account_name"],
        "narration": data.get("narration", ""),
        "reference": reference,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        withdrawal_id = None
        try:
            result = db.table("wallet_withdrawals").insert(record)
            withdrawal_row = result[0] if isinstance(result, list) else result
            withdrawal_id = withdrawal_row.get("id")
        except Exception as tbl_exc:
            err = str(tbl_exc)
            if "does not exist" not in err and "schema cache" not in err and "relation" not in err:
                raise

        db.table("wallets").eq("user_id", g.user_id).update({
            "balance": balance - amount,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        db.table("wallet_transactions").insert({
            "user_id": g.user_id,
            "type": "debit",
            "amount": amount,
            "balance_after": balance - amount,
            "reason": f"Withdrawal request {reference}",
            "reference_type": "withdrawal",
            "reference_id": withdrawal_id,
            "metadata": {"reference": reference, "status": "pending"},
        })

        return jsonify({
            "message": "Withdrawal request submitted. Processing within 1-2 business days.",
            "reference": reference,
            "amount": amount,
            "status": "pending",
        }), 201

    except Exception as exc:
        return jsonify({"error": f"Withdrawal request failed: {str(exc)[:120]}"}), 500


@wallet_bp.route("/transactions", methods=["GET"])
@require_auth
def wallet_transactions():
    """
    Get wallet transaction history.
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
    responses:
      200:
        description: Wallet transaction history
    """
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    txns = get_wallet_transactions(g.user_id, limit=limit, offset=offset)
    return jsonify(txns), 200
