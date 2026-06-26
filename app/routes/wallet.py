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
    return jsonify({
        "balance": float(wallet.get("balance", 0)),
        "currency": wallet.get("currency", "NGN"),
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
    amount = float(data.get("amount", 0))
    if amount < 100:
        return jsonify({"error": "Minimum top-up is ₦100"}), 400

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
