"""
Webhook routes — Paystack payment webhooks.
All payment confirmation is handled here. Never trust client-side success.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from app.db import get_db
from app.services.order_service import confirm_order_payment
from app.services.wallet_service import credit_wallet
from app.services.notification_service import send_notification

webhooks_bp = Blueprint("webhooks", __name__)


@webhooks_bp.route("/paystack", methods=["POST"])
def paystack_webhook():
    """
    Paystack webhook handler.
    Handles: charge.success, transfer.success, dedicatedaccount.assign.success
    ---
    tags: [Webhooks]
    security: []
    responses:
      200:
        description: Webhook processed
    """
    payload_bytes = request.get_data()
    signature = request.headers.get("x-paystack-signature", "")

    secret = current_app.config.get("PAYSTACK_WEBHOOK_SECRET", "")
    if secret:
        computed = hmac.new(secret.encode(), payload_bytes, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature):
            return jsonify({"error": "Invalid signature"}), 401

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference") or data.get("transfer_code", "")
    idempotency_key = f"paystack:{event_type}:{reference}"

    try:
        if event_type == "charge.success":
            _handle_charge_success(data)
        elif event_type == "dedicatedaccount.assign.success":
            _handle_dva_assign(data)
        elif event_type == "transfer.success":
            _handle_transfer(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "ok"}), 200


def _handle_charge_success(data: dict):
    """
    Handle successful card charge. Routes to:
    - Order payment confirmation if metadata.type == 'order_payment'
    - Wallet top-up if metadata.type == 'wallet_topup'
    """
    reference = data.get("reference")
    metadata = data.get("metadata", {})
    amount_kobo = data.get("amount", 0)
    amount_naira = amount_kobo / 100

    payment_type = metadata.get("type")
    user_id = metadata.get("user_id")

    if payment_type == "order_payment":
        order_id = metadata.get("order_id")
        if order_id:
            confirm_order_payment(order_id, reference, provider_response=data)

    elif payment_type == "wallet_topup" and user_id:
        credit_wallet(
            user_id=user_id,
            amount=amount_naira,
            payment_reference=reference,
            reference_type="topup",
            notes=f"Card top-up via Paystack ({reference})",
            provider_response=data,
        )
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded",
            title=f"Wallet Funded ₦{amount_naira:,.0f}",
            body=f"Your wallet has been credited with ₦{amount_naira:,.0f}.",
            channels=["in_app", "email"],
        )


def _handle_dva_assign(data: dict):
    """
    Handle dedicated virtual account assignment. Update wallet record.
    """
    customer = data.get("customer", {})
    account = data.get("dedicated_account", {})
    user_email = customer.get("email")
    if not user_email:
        return
    db = get_db()
    user_rows = db.table("profiles").select("id").eq("email", user_email).limit(1).execute()
    if not user_rows:
        return
    user_id = user_rows[0]["id"]
    db.table("virtual_accounts").eq("user_id", user_id).update({
        "account_number": account.get("account_number"),
        "bank_name": account.get("bank", {}).get("name"),
        "account_name": account.get("account_name"),
        "provider_customer_id": customer.get("customer_code"),
    })


def _handle_transfer(data: dict):
    """Bank transfer credited to virtual account → credit wallet."""
    reference = data.get("reference")
    amount_kobo = data.get("amount", 0)
    amount_naira = amount_kobo / 100
    recipient = data.get("recipient", {})

    db = get_db()
    account_number = recipient.get("details", {}).get("account_number")
    if not account_number:
        return

    va_rows = db.table("virtual_accounts").select("user_id").eq("account_number", account_number).limit(1).execute()
    wallet = {"user_id": va_rows[0]["user_id"]} if va_rows else None
    if not wallet:
        return

    user_id = wallet["user_id"]
    credit_wallet(
        user_id=user_id,
        amount=amount_naira,
        payment_reference=reference,
        reference_type="bank_transfer",
        notes=f"Bank transfer credited ({reference})",
    )
    send_notification(
        user_id=user_id,
        notif_type="wallet_funded",
        title=f"Wallet Credited ₦{amount_naira:,.0f}",
        body=f"Your bank transfer of ₦{amount_naira:,.0f} has been confirmed.",
        channels=["in_app", "email"],
    )
