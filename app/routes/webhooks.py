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
from app.db import get_db, SupabaseError
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
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    reference = data.get("reference") or data.get("transfer_code")
    if not reference:
        if data.get("id"):
            reference = f"id_{data.get('id')}"
        elif payload.get("id"):
            reference = f"evt_{payload.get('id')}"
        elif payload.get("event_id"):
            reference = f"evt_{payload.get('event_id')}"
        else:
            # Fallback to stable SHA-256 hash of raw payload bytes to ensure idempotency when all references are missing
            reference = "hash_" + hashlib.sha256(payload_bytes).hexdigest()

    # Atomic Idempotency Claim
    try:
        get_db().table("webhook_events").insert({
            "provider": "paystack",
            "event_type": event_type,
            "reference": reference,
            "payload": payload,
            "status": "processing",
        }).execute()
    except SupabaseError as err:
        err_str = str(err)
        if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
            return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
        raise

    try:
        if event_type == "charge.success":
            _handle_charge_success(data)
        elif event_type == "dedicatedaccount.assign.success":
            _handle_dva_assign(data)
        elif event_type == "transfer.success":
            _handle_transfer(data)

        # Mark as processed
        if reference:
            get_db().table("webhook_events").eq("provider", "paystack").eq("event_type", event_type).eq("reference", reference).update({
                "status": "processed",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as e:
        # Mark as failed
        if reference:
            try:
                get_db().table("webhook_events").eq("provider", "paystack").eq("event_type", event_type).eq("reference", reference).update({
                    "status": "failed",
                    "error": str(e),
                }).execute()
            except Exception:
                pass
        _notify_admin_webhook_failure(event_type, reference, str(e))
        return jsonify({"error": "Webhook processing failed"}), 500

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

    reference = data.get("tx_ref") or data.get("flw_ref")
    if not reference:
        if data.get("id"):
            reference = f"id_{data.get('id')}"
        elif payload.get("id"):
            reference = f"evt_{payload.get('id')}"
        elif payload.get("event_id"):
            reference = f"evt_{payload.get('event_id')}"
        else:
            # Fallback to stable SHA-256 hash of raw payload bytes to ensure idempotency when all references are missing
            reference = "hash_" + hashlib.sha256(payload_bytes).hexdigest()

    # Atomic Idempotency Claim
    try:
        get_db().table("webhook_events").insert({
            "provider": "flutterwave",
            "event_type": event_type,
            "reference": reference,
            "payload": payload,
            "status": "processing",
        }).execute()
    except SupabaseError as err:
        err_str = str(err)
        if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
            return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
        raise

    try:
        if event_type == "charge.completed" and data.get("status") == "successful":
            _handle_flutterwave_charge_success(data)

        # Mark as processed
        if reference:
            get_db().table("webhook_events").eq("provider", "flutterwave").eq("event_type", event_type).eq("reference", reference).update({
                "status": "processed",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
    except Exception as e:
        # Mark as failed
        if reference:
            try:
                get_db().table("webhook_events").eq("provider", "flutterwave").eq("event_type", event_type).eq("reference", reference).update({
                    "status": "failed",
                    "error": str(e),
                }).execute()
            except Exception:
                pass
        _notify_admin_webhook_failure(event_type, reference, str(e))
        return jsonify({"error": "Webhook processing failed"}), 500

    return jsonify({"message": MSG.WEBHOOK_OK}), 200


def _handle_flutterwave_charge_success(data: dict):
    """
    Handle a successful Flutterwave charge. Routes to:
    - Order payment confirmation if meta.type == 'order_payment'
    - Wallet top-up if meta.type == 'wallet_topup'
    """
    currency = data.get("currency")
    if currency and str(currency).upper() != "NGN":
        raise ValueError(f"Invalid currency: {currency}")

    reference = data.get("tx_ref") or data.get("flw_ref")
    meta = data.get("meta") or data.get("metadata") or {}
    amount_naira = float(data.get("amount", 0))
    if amount_naira <= 0:
        raise ValueError("Invalid payment amount")

    payment_type = meta.get("type")
    user_id = meta.get("user_id")

    db = get_db()

    if payment_type == "order_payment":
        order_id = meta.get("order_id")
        if not order_id:
            raise ValueError("Missing order_id in metadata")

        order = db.table("orders").select("id,user_id,total_amount,status,payment_status,campus_id").eq("id", order_id).single().execute()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.get("user_id") and str(order.get("user_id")) != str(user_id):
            raise ValueError("Order user mismatch")

        expected_amount = float(order.get("total_amount") or 0)
        if abs(amount_naira - expected_amount) > 0.01:
            raise ValueError(f"Amount mismatch. Webhook: {amount_naira}, Order: {expected_amount}")

        if order.get("status") in ("cancelled", "refunded"):
            raise ValueError(f"Order is already {order.get('status')}")

        confirm_order_payment(order_id, reference, provider_response=data)

    elif payment_type == "wallet_topup" and user_id:
        if amount_naira <= 0:
            raise ValueError(f"Invalid top-up amount: {amount_naira}")

        profile = db.table("profiles").select("id,campus_id").eq("id", user_id).single().execute()
        if not profile:
            raise ValueError(f"User {user_id} not found for wallet top-up")

        campus_id = profile.get("campus_id")
        credit_wallet(
            user_id=user_id,
            amount=amount_naira,
            payment_reference=reference,
            reference_type="topup",
            notes=f"Card top-up via Flutterwave ({reference})",
            provider_response=data,
            campus_id=campus_id,
        )
        _fmt_amt = f"{amount_naira:,.0f}"
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded_card",
            template_data={"amount": _fmt_amt},
            campus_id=campus_id,
        )


def _handle_charge_success(data: dict):
    """
    Handle successful card charge. Routes to:
    - Order payment confirmation if metadata.type == 'order_payment'
    - Wallet top-up if metadata.type == 'wallet_topup'
    """
    currency = data.get("currency")
    if currency and str(currency).upper() != "NGN":
        raise ValueError(f"Invalid currency: {currency}")

    reference = data.get("reference")
    metadata = data.get("metadata", {})
    amount_kobo = data.get("amount", 0)
    amount_naira = amount_kobo / 100
    if amount_naira <= 0:
        raise ValueError("Invalid payment amount")

    payment_type = metadata.get("type")
    user_id = metadata.get("user_id")

    db = get_db()

    if payment_type == "order_payment":
        order_id = metadata.get("order_id")
        if not order_id:
            raise ValueError("Missing order_id in metadata")

        order = db.table("orders").select("id,user_id,total_amount,status,payment_status,campus_id").eq("id", order_id).single().execute()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.get("user_id") and str(order.get("user_id")) != str(user_id):
            raise ValueError("Order user mismatch")

        expected_amount = float(order.get("total_amount") or 0)
        if abs(amount_naira - expected_amount) > 0.01:
            raise ValueError(f"Amount mismatch. Webhook: {amount_naira}, Order: {expected_amount}")

        if order.get("status") in ("cancelled", "refunded"):
            raise ValueError(f"Order is already {order.get('status')}")

        confirm_order_payment(order_id, reference, provider_response=data)

    elif payment_type == "wallet_topup" and user_id:
        if amount_naira <= 0:
            raise ValueError(f"Invalid top-up amount: {amount_naira}")

        profile = db.table("profiles").select("id,campus_id").eq("id", user_id).single().execute()
        if not profile:
            raise ValueError(f"User {user_id} not found for wallet top-up")

        campus_id = profile.get("campus_id")
        credit_wallet(
            user_id=user_id,
            amount=amount_naira,
            payment_reference=reference,
            reference_type="topup",
            notes=f"Card top-up via Paystack ({reference})",
            provider_response=data,
            campus_id=campus_id,
        )
        _fmt_amt = f"{amount_naira:,.0f}"
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded_card",
            template_data={"amount": _fmt_amt},
            campus_id=campus_id,
        )


def _handle_dva_assign(data: dict):
    """
    Handle dedicated virtual account assignment. Update or insert wallet record.
    """
    customer = data.get("customer", {})
    account = data.get("dedicated_account", {})
    user_email = customer.get("email")
    if not user_email:
        return
    db = get_db()
    user_rows = db.table("profiles").select("id,campus_id").eq("email", user_email).limit(1).execute()
    if not user_rows:
        return
    user_id = user_rows[0]["id"]
    campus_id = user_rows[0].get("campus_id")

    existing_va = db.table("virtual_accounts").select("id").eq("user_id", user_id).limit(1).execute()
    if existing_va:
        update_data = {
            "account_number": account.get("account_number"),
            "bank_name": account.get("bank", {}).get("name"),
            "account_name": account.get("account_name"),
            "provider_customer_id": customer.get("customer_code"),
            "campus_id": campus_id,
        }
        db.table("virtual_accounts").eq("user_id", user_id).update(update_data).execute()
    else:
        va_data = {
            "user_id": user_id,
            "account_number": account.get("account_number"),
            "bank_name": account.get("bank", {}).get("name"),
            "account_name": account.get("account_name"),
            "provider_customer_id": customer.get("customer_code"),
            "provider_reference": str(account.get("id", "")),
            "provider": "paystack",
            "campus_id": campus_id,
        }
        db.table("virtual_accounts").insert(va_data).execute()


def _handle_transfer(data: dict):
    """Bank transfer credited to virtual account → credit wallet."""
    reference = data.get("reference")
    amount_kobo = data.get("amount", 0)
    amount_naira = amount_kobo / 100
    recipient = data.get("recipient", {})

    db = get_db()
    account_number = recipient.get("details", {}).get("account_number")
    if not account_number:
        err_msg = f"Bank transfer webhook error: missing account_number in recipient details for ref {reference}"
        current_app.logger.error(err_msg)
        _notify_admin_webhook_failure("transfer.success", str(reference), err_msg)
        raise ValueError(err_msg)

    va_rows = db.table("virtual_accounts").select("user_id,campus_id").eq("account_number", account_number).limit(1).execute()
    if not va_rows:
        current_app.logger.error("No virtual account found for account_number %s", account_number)
        try:
            from app.constants import ADMIN_ROLES
            admins = db.table("profiles").select("id").in_("role", list(ADMIN_ROLES)).execute() or []
            for admin in admins:
                send_notification(
                    user_id=admin["id"],
                    notif_type="system_alert",
                    title="Unlinked Bank Transfer Warning",
                    body=f"Bank transfer of ₦{amount_naira:,.2f} received for unknown account number {account_number} (ref: {reference}).",
                    reference_id=reference,
                    reference_type="bank_transfer",
                )
        except Exception as ae:
            current_app.logger.error("Failed to notify admins: %s", ae)

        # Then raise error (don't use return)
        err_msg = f"Bank transfer webhook error: no virtual account found for account_number {account_number} (ref {reference})"
        current_app.logger.error(err_msg)
        _notify_admin_webhook_failure("transfer.success", str(reference), err_msg)
        raise ValueError(err_msg)  # <- This stops the function

    user_id = va_rows[0]["user_id"]
    campus_id = va_rows[0].get("campus_id")
    if not campus_id:
        p_rows = db.table("profiles").select("campus_id").eq("id", user_id).limit(1).execute()
        campus_id = p_rows[0].get("campus_id") if p_rows else None

    credit_wallet(
        user_id=user_id,
        amount=amount_naira,
        payment_reference=reference,
        reference_type="bank_transfer",
        notes=f"Bank transfer credited ({reference})",
        campus_id=campus_id,
    )
    _fmt_amt = f"{amount_naira:,.0f}"
    send_notification(
        user_id=user_id,
        notif_type="wallet_funded_bank",
        template_data={"amount": _fmt_amt},
        campus_id=campus_id,
    )


def _notify_admin_webhook_failure(event_type: str, reference: str, error: str) -> None:
    """Send push+in_app alert to all admins when a webhook event fails to process."""
    try:
        from app.constants import ADMIN_ROLES
        db = get_db()
        admins = (
            db.table("profiles")
            .select("id")
            .in_("role", list(ADMIN_ROLES))
            .eq("is_active", True)
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
