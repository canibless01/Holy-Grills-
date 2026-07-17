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
from app.messages import MSG
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
            return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401
    elif not current_app.config.get("DEBUG"):
        # No webhook secret configured — never trust an unsigned payment
        # webhook outside of local debug development. Fail closed rather
        # than silently accepting money-moving events with no verification.
        current_app.logger.error("PAYSTACK_WEBHOOK_SECRET not configured — rejecting unsigned webhook")
        return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return jsonify({"error": MSG.WEBHOOK_INVALID_JSON}), 400

    event_type = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference") or data.get("transfer_code", "")

    # Idempotency guard: reject duplicate webhook deliveries for events that carry
    # a payment reference. Paystack retries on 5xx, so a transient server error
    # could cause the same charge.success / transfer.success to arrive twice.
    if reference and event_type in ("charge.success", "transfer.success"):
        try:
            already = (
                get_db()
                .table("payments")
                .select("id")
                .eq("reference", reference)
                .limit(1)
                .execute()
            )
            if already:
                return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
        except Exception:
            pass  # If the idempotency check itself fails, allow processing to continue

    try:
        if event_type == "charge.success":
            _handle_charge_success(data)
        elif event_type == "dedicatedaccount.assign.success":
            _handle_dva_assign(data)
        elif event_type == "transfer.success":
            _handle_transfer(data)
    except Exception as e:
        _audit_webhook_event(event_type, reference, payload, error=str(e))
        _notify_admin_webhook_failure(event_type, reference, str(e))
        return jsonify({"error": str(e)}), 500

    _audit_webhook_event(event_type, reference, payload)
    return jsonify({"message": MSG.WEBHOOK_OK}), 200


@webhooks_bp.route("/flutterwave", methods=["POST"])
def flutterwave_webhook():
    """
    Flutterwave webhook handler.
    Handles: charge.completed (order payment / wallet top-up).
    ---
    tags: [Webhooks]
    security: []
    responses:
      200:
        description: Webhook processed
      401:
        description: Invalid signature
    """
    payload_bytes = request.get_data()
    signature = request.headers.get("verif-hash", "")

    secret = current_app.config.get("FLUTTERWAVE_WEBHOOK_SECRET", "")
    if secret:
        if not hmac.compare_digest(signature, secret):
            return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401
    elif not current_app.config.get("DEBUG"):
        # No webhook secret configured — never trust an unsigned payment
        # webhook outside of local debug development. Fail closed rather
        # than silently accepting money-moving events with no verification.
        current_app.logger.error("FLUTTERWAVE_WEBHOOK_SECRET not configured — rejecting unsigned webhook")
        return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return jsonify({"error": MSG.WEBHOOK_INVALID_JSON}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": MSG.WEBHOOK_INVALID_JSON}), 400

    event_type = payload.get("event")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    reference = data.get("tx_ref") or data.get("flw_ref", "")

    # Idempotency guard, mirrors the Paystack handler above.
    if reference and event_type == "charge.completed":
        try:
            already = (
                get_db()
                .table("payments")
                .select("id")
                .eq("reference", reference)
                .limit(1)
                .execute()
            )
            if already:
                return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
        except Exception:
            pass

    try:
        if event_type == "charge.completed" and data.get("status") == "successful":
            _handle_flutterwave_charge_success(data)
    except Exception as e:
        _audit_webhook_event(event_type, reference, payload, error=str(e))
        _notify_admin_webhook_failure(event_type, reference, str(e))
        return jsonify({"error": str(e)}), 500

    _audit_webhook_event(event_type, reference, payload)
    return jsonify({"message": MSG.WEBHOOK_OK}), 200


def _handle_flutterwave_charge_success(data: dict):
    """
    Handle a successful Flutterwave charge. Routes to:
    - Order payment confirmation if meta.type == 'order_payment'
    - Wallet top-up if meta.type == 'wallet_topup'
    """
    reference = data.get("tx_ref") or data.get("flw_ref")
    meta = data.get("meta") or data.get("metadata") or {}
    amount_naira = data.get("amount", 0)

    payment_type = meta.get("type")
    user_id = meta.get("user_id")

    if payment_type == "order_payment":
        order_id = meta.get("order_id")
        if order_id:
            confirm_order_payment(order_id, reference, provider_response=data)

    elif payment_type == "wallet_topup" and user_id:
        credit_wallet(
            user_id=user_id,
            amount=amount_naira,
            payment_reference=reference,
            reference_type="topup",
            notes=f"Card top-up via Flutterwave ({reference})",
            provider_response=data,
        )
        _fmt_amt = f"{amount_naira:,.0f}"
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded_card",
            template_data={"amount": _fmt_amt},
        )


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
        _fmt_amt = f"{amount_naira:,.0f}"
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded_card",
            template_data={"amount": _fmt_amt},
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
    _fmt_amt = f"{amount_naira:,.0f}"
    send_notification(
        user_id=user_id,
        notif_type="wallet_funded_bank",
        template_data={"amount": _fmt_amt},
    )


def _audit_webhook_event(event_type: str, reference: str, payload: dict, error: str = None) -> None:
    """Write a webhook_events audit row. Fire-and-forget — never raises."""
    try:
        get_db().table("webhook_events").insert({
            "event_type": event_type,
            "reference": reference or "",
            "payload": payload,
            "error": error,
            "status": "failed" if error else "processed",
        })
    except Exception:
        pass


def _notify_admin_webhook_failure(event_type: str, reference: str, error: str) -> None:
    """Send push+in_app alert to all admins when a webhook event fails to process."""
    try:
        db = get_db()
        admins = (
            db.table("profiles")
            .select("id")
            .eq("role", "admin")
            .eq("is_active", "true")
            .execute()
        ) or []
        from app.messages import MSG
        for admin in admins:
            send_notification(
                user_id=admin["id"],
                notif_type="webhook_failure",
                template_data={
                    "event_type": event_type,
                    "reference": reference or "N/A",
                    "error": error[:200],
                },
            )
    except Exception:
        pass
