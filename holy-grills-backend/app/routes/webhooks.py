"""
Payment-provider webhooks (Paystack + Flutterwave): signature check, atomic idempotency claim, event routing.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from app.db import get_db, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)
from app.services.order_service import confirm_order_payment
from app.services.wallet_service import credit_wallet
from app.services.notification_service import send_notification
from app.services.payment_amounts import expected_from_metadata, validate_charge_amount

webhooks_bp = Blueprint("webhooks", __name__)

# Provider event log statuses. The provider only ever retries a delivery we answered
# with a non-2xx; anything already `processed` is acknowledged without re-applying.
WEBHOOK_PROCESSING = "processing"
WEBHOOK_PROCESSED = "processed"
WEBHOOK_FAILED = "failed"


def _claim_provider_event(provider, event_type, reference, payload):
    """A failed delivery can retry; an in-flight delivery is not acknowledged as done."""
    db = get_db()
    try:
        db.table("webhook_events").insert({"provider": provider, "event_type": event_type,
            "reference": reference, "payload": payload, "status": "processing"})
        return "claimed"
    except SupabaseError as exc:
        text = str(exc).lower()
        if not any(marker in text for marker in ("23505", "duplicate", "unique")):
            raise
    query = lambda: db.table("webhook_events").eq("provider", provider).eq("event_type", event_type).eq("reference", reference)
    claimed = query().eq("status", "failed").update({"status": "processing", "error": None, "processed_at": None, "payload": payload})
    if claimed:
        return "claimed"
    row = query().select("status").single().execute() or {}
    return "processed" if row.get("status") == "processed" else "busy"


def _campus_for_payload(payload: dict):
    """Best-effort campus for a provider event, including the ones that are about to fail.

    A webhook row is only scoped to a campus when processing *succeeds* — the campus id
    comes back from the handler. A failed event therefore used to be stored with
    `campus_id = NULL`, and because the admin webhook log is campus-scoped, the very
    deliveries an admin needs to see were invisible to every campus admin. Resolve it
    from the payload when the handler never got that far.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    meta = data.get("metadata") or data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    if meta.get("campus_id"):
        return meta.get("campus_id")
    db = get_db()
    try:
        if meta.get("order_id"):
            row = db.table("orders").select("campus_id").eq("id", meta["order_id"]).single().execute()
            if row and row.get("campus_id"):
                return row["campus_id"]
        if meta.get("ticket_id"):
            row = db.table("event_tickets").select("campus_id").eq("id", meta["ticket_id"]).single().execute()
            if row and row.get("campus_id"):
                return row["campus_id"]
        if meta.get("user_id"):
            row = db.table("profiles").select("campus_id").eq("id", meta["user_id"]).single().execute()
            if row and row.get("campus_id"):
                return row["campus_id"]
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("webhook failure: campus lookup for ref %s failed: %s",
                       data.get("reference") or data.get("tx_ref"), exc)
    return None


def _mark_event(provider, event_type, reference, fields):
    """Update one webhook_events row, never letting a logging failure mask the outcome."""
    if not reference:
        return
    try:
        (get_db().table("webhook_events")
         .eq("provider", provider).eq("event_type", event_type).eq("reference", reference)
         .update(fields).execute())
    except Exception as exc:                                  # noqa: BLE001
        logger.error("webhook_events update failed (%s, %s, ref %s): %s",
                     provider, event_type, reference, exc)


def _record_event_failure(provider, event_type, reference, payload, error):
    """Persist a failed delivery so it is visible (and retryable) in the admin log."""
    fields = {"status": WEBHOOK_FAILED, "error": str(error)}
    campus_id = _campus_for_payload(payload)
    if campus_id:
        fields["campus_id"] = campus_id
    _mark_event(provider, event_type, reference, fields)
    return campus_id


def _process_provider_event(provider, event_type, data):
    """Route one provider payload to its handler. Raises on any unrecoverable problem."""
    if provider == "paystack":
        if event_type == "charge.success":
            return _handle_charge_success(data)
        if event_type == "dedicatedaccount.assign.success":
            return _handle_dva_assign(data)
        if event_type == "transfer.success":
            return _handle_transfer(data)
        return None
    if provider == "flutterwave":
        if event_type == "charge.completed" and data.get("status") == "successful":
            return _handle_flutterwave_charge_success(data)
    return None


def reprocess_stored_event(provider, event_type, payload):
    """Replay one stored provider payload through the normal routing.

    Used by the admin webhook log's retry action. Safe to repeat: every handler is
    idempotent, so an already-confirmed order/ticket/purchase is returned untouched.
    """
    if not isinstance(payload, dict):
        raise ValueError("Stored webhook payload is missing or not an object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Stored webhook payload has no data object")
    resolved = _process_provider_event(provider, event_type, data)
    if resolved is None:
        resolved = _campus_for_payload(payload)
    return resolved


def _confirm_event_ticket_charge(db, metadata, reference, data, provider):
    """Confirm an event ticket after a provider-verified charge.

    The amount check is the fee-aware one used by orders: Paystack adds its gateway fee
    to the settled amount whenever the customer bears it, so an exact comparison failed
    every such ticket and left a paid registrant stuck on `payment_status = pending`
    (invisible on the registrant list and in the email to the host).
    """
    ticket_id = metadata.get("ticket_id")
    if not ticket_id:
        raise ValueError("Missing ticket_id in metadata")
    ticket = (db.table("event_tickets")
              .select("id,user_id,card_amount_used,status,payment_status,campus_id")
              .eq("id", ticket_id).single().execute())
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")
    meta_user_id = metadata.get("user_id")
    if meta_user_id and ticket.get("user_id") and str(ticket.get("user_id")) != str(meta_user_id):
        raise ValueError("Ticket user mismatch")
    if ticket.get("payment_status") == "paid":
        logger.warning(
            "Duplicate payment webhook for already-paid ticket %s (ref %s) — skipping",
            ticket_id, reference,
        )
        return ticket.get("campus_id")

    expected_amount = float(ticket.get("card_amount_used") or 0)
    breakdown = validate_charge_amount(data, expected_amount, provider, label="Event ticket")
    if str(ticket.get("status") or "").lower() in ("cancelled", "canceled", "expired"):
        raise ValueError(
            f"Ticket {ticket_id} was cancelled/expired before its card payment arrived "
            f"(ref {reference}: ₦{float(breakdown.get('paid_kobo') or 0) / 100:,.2f} paid). "
            "Refund this charge or re-issue the ticket."
        )

    from app.routes.events import confirm_event_ticket_payment
    confirm_event_ticket_payment(
        ticket_id, reference,
        provider_response={**data, "_amount_breakdown": breakdown},
    )
    return ticket.get("campus_id")


def _complete_marketplace_charge(db, metadata, reference, data, provider):
    """Complete a marketplace purchase after a provider-verified charge.

    Uses `complete_marketplace_card_purchase` (not the raw helper) so a purchase that
    cannot be completed after the card was charged — sold out, price changed, HP or
    wallet fell short — is refunded to the buyer's wallet instead of being silently
    dropped by a failed webhook.
    """
    user_id = metadata.get("user_id")
    listing_id = metadata.get("listing_id")
    if not user_id or not listing_id:
        raise ValueError("Missing marketplace purchase metadata (user_id/listing_id)")

    expected_amount = expected_from_metadata(metadata, data, provider)
    if expected_amount is None or expected_amount <= 0:
        # A payment initialized before we recorded the expected amount. Nothing local to
        # reconcile against, so accept the charge and say so loudly rather than strand it.
        expected_amount = (float(data.get("amount") or 0) / 100 if provider == "paystack"
                           else float(data.get("amount") or 0))
        logger.warning(
            "marketplace webhook %s has no recorded expected amount; accepting ₦%.2f as charged",
            reference, expected_amount,
        )
    else:
        validate_charge_amount(data, expected_amount, provider, label="Marketplace purchase")

    from app.routes.marketplace import complete_marketplace_card_purchase
    created = complete_marketplace_card_purchase(
        user_id=user_id,
        listing_id=listing_id,
        quantity=metadata.get("quantity", 1),
        wallet_amount=metadata.get("wallet_amount", 0.0),
        pay_with_hp=metadata.get("pay_with_hp", False),
        payment_reference=reference,
        amount_paid=expected_amount,
        refund_amount=expected_amount,
    )
    purchase = created[0] if isinstance(created, tuple) else created
    return (purchase or {}).get("campus_id")


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

    # Paystack signs webhooks with the account's *secret key* (there is no separate webhook secret), so fall back to
    # PAYSTACK_SECRET_KEY when PAYSTACK_WEBHOOK_SECRET isn't set -- otherwise every real webhook is rejected with 401
    # and no top-up is ever credited.
    secret = current_app.config.get("PAYSTACK_WEBHOOK_SECRET") or current_app.config.get("PAYSTACK_SECRET_KEY", "")
    if secret:
        computed = hmac.new(secret.encode(), payload_bytes, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature):
            return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401
    elif not current_app.config.get("ALLOW_UNSIGNED_WEBHOOKS"):
        current_app.logger.error("PAYSTACK_WEBHOOK_SECRET not configured — rejecting unsigned webhook")
        return jsonify({"error": MSG.WEBHOOK_INVALID_SIGNATURE}), 401

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return jsonify({"error": MSG.WEBHOOK_INVALID_JSON}), 400
    if not isinstance(payload, dict):      # a JSON array/scalar used to raise AttributeError -> 500 (Flutterwave already guarded this)
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

    claim = _claim_provider_event("paystack", event_type, reference, payload)
    if claim == "processed":
        return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
    if claim == "busy":
        return jsonify({"error": MSG.WEBHOOK_IN_PROGRESS}), 503

    try:
        resolved_campus_id = _process_provider_event("paystack", event_type, data)

        update_fields = {
            "status": WEBHOOK_PROCESSED,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        if resolved_campus_id:
            update_fields["campus_id"] = resolved_campus_id
        _mark_event("paystack", event_type, reference, update_fields)
    except Exception as e:
        _record_event_failure("paystack", event_type, reference, payload, e)
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
    elif not current_app.config.get("ALLOW_UNSIGNED_WEBHOOKS"):
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

    claim = _claim_provider_event("flutterwave", event_type, reference, payload)
    if claim == "processed":
        return jsonify({"message": MSG.WEBHOOK_ALREADY_PROCESSED}), 200
    if claim == "busy":
        return jsonify({"error": MSG.WEBHOOK_IN_PROGRESS}), 503

    try:
        resolved_campus_id = _process_provider_event("flutterwave", event_type, data)

        update_fields = {
            "status": WEBHOOK_PROCESSED,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
        if resolved_campus_id:
            update_fields["campus_id"] = resolved_campus_id
        _mark_event("flutterwave", event_type, reference, update_fields)
    except Exception as e:
        _record_event_failure("flutterwave", event_type, reference, payload, e)
        _notify_admin_webhook_failure(event_type, reference, str(e))
        return jsonify({"error": "Webhook processing failed"}), 500

    return jsonify({"message": MSG.WEBHOOK_OK}), 200


def _handle_flutterwave_charge_success(data: dict):
    """
    Handle a successful Flutterwave charge. Routes to:
    - Order payment confirmation if meta.type == 'order_payment'
    - Wallet top-up if meta.type == 'wallet_topup'
    - HP bundle isolation (must not be credited as order/wallet)
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
    purpose = meta.get("purpose")
    user_id = meta.get("user_id")

    db = get_db()

    # B-4 isolation: HP bundle references must not be credited as order or wallet
    if purpose == "hp_bundle" or payment_type == "hp_bundle":
        # Treat as already handled or handle via same logic as Paystack if needed
        # Since Flutterwave is not currently used for HP bundles, just return campus to mark processed
        # and ensure it doesn't fall through to wallet top-up.
        try:
            profile = db.table("profiles").select("campus_id").eq("id", user_id).single().execute() if user_id else None
            return (profile or {}).get("campus_id")
        except Exception:
            return None

    if payment_type == "order_payment":
        order_id = meta.get("order_id")
        if not order_id:
            raise ValueError("Missing order_id in metadata")
        order = db.table("orders").select("*").eq("id", order_id).single().execute()
        if not order:
            raise ValueError("Order not found")
        # Confirmation validates currency, owner, campus, reference and the card
        # remainder (not the full basket when a wallet contribution exists).
        confirm_order_payment(order_id, reference, provider_response=data, provider="flutterwave")
        return order.get("campus_id")

    elif payment_type == "event_ticket_payment":
        return _confirm_event_ticket_charge(db, meta, reference, data, "flutterwave")

    elif payment_type == "marketplace_purchase":
        return _complete_marketplace_charge(db, meta, reference, data, "flutterwave")

    elif payment_type == "wallet_topup" and not user_id:
        # A top-up reference without an owner used to fall through to `return None`, which
        # marked the delivery "processed" while nobody was credited. Fail loudly instead.
        raise ValueError(f"Wallet top-up {reference} has no user_id in its metadata")

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
        try:
            send_notification(
                user_id=user_id,
                notif_type="wallet_funded_card",
                template_data={"amount": _fmt_amt},
                campus_id=campus_id,
            )
        except Exception as exc:
            # [D10] the wallet is already credited -- a notification failure must not turn this into a "failed" event
            current_app.logger.error("Post-payment notification failed for %s (payment already confirmed): %s", reference, exc)
        return campus_id
    return None


def _handle_charge_success(data: dict):
    """
    Handle successful card charge. Routes to:
    - Order payment confirmation if metadata.type == 'order_payment'
    - Wallet top-up if metadata.type == 'wallet_topup'
    - HP bundle purchase if metadata.purpose == 'hp_bundle' or type == 'hp_bundle' (isolated)
    """
    currency = data.get("currency")
    if currency and str(currency).upper() != "NGN":
        raise ValueError(f"Invalid currency: {currency}")

    reference = data.get("reference")
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):     # Paystack sends metadata: null (or a string) on bank-transfer charges
        metadata = {}
    authorization = data.get("authorization")
    if not isinstance(authorization, dict):
        authorization = {}
    amount_kobo = data.get("amount", 0)
    amount_naira = amount_kobo / 100
    if amount_naira <= 0:
        raise ValueError("Invalid payment amount")

    payment_type = metadata.get("type")
    purpose = metadata.get("purpose")
    user_id = metadata.get("user_id")

    db = get_db()

    # B-4: HP bundle isolation — a reference created for HP bundle must never be credited as order or wallet top-up
    if purpose == "hp_bundle" or payment_type == "hp_bundle":
        # Ensure this reference is not processed as order or wallet elsewhere; handle as HP bundle
        try:
            hp_amount = int(metadata.get("hp_amount") or 0)
        except (TypeError, ValueError):
            hp_amount = 0
        if not user_id or hp_amount <= 0:
            raise ValueError("Invalid HP bundle metadata in webhook")

        # Idempotency: if already recorded in hp_bundle_purchases, skip
        try:
            existing = db.table("hp_bundle_purchases").select("id").eq("provider", "paystack").eq("provider_reference", reference).execute()
            if existing:
                # Already processed via purchase endpoint or previous webhook
                profile = db.table("profiles").select("campus_id").eq("id", user_id).single().execute()
                return (profile or {}).get("campus_id")
        except Exception:
            pass  # proceed to attempt credit; RPC will handle duplicate

        # Price check: fee-aware, exactly like orders (the customer may have been charged
        # the gateway fee on top of the bundle price).
        price_per_hp = float(current_app.config.get("HP_BUNDLE_PRICE_PER_HP", 5.0))
        expected_naira = hp_amount * price_per_hp
        validate_charge_amount(data, expected_naira, "paystack", label="HP bundle")

        try:
            from app.services.hp_service import process_hp_bundle_purchase
            process_hp_bundle_purchase(
                event_host_id=user_id,
                hp_amount=hp_amount,
                naira_paid=amount_naira,
                provider="paystack",
                provider_reference=reference,
            )
            profile = db.table("profiles").select("campus_id").eq("id", user_id).single().execute()
            return (profile or {}).get("campus_id")
        except Exception as e:
            # If already processed race, treat as success
            if "already processed" in str(e).lower():
                profile = db.table("profiles").select("campus_id").eq("id", user_id).single().execute()
                return (profile or {}).get("campus_id")
            raise

    if payment_type == "order_payment":
        order_id = metadata.get("order_id")
        if not order_id:
            raise ValueError("Missing order_id in metadata")
        order = db.table("orders").select("*").eq("id", order_id).single().execute()
        if not order:
            raise ValueError("Order not found")
        # Confirmation validates currency, owner, campus, reference and the card
        # remainder (not the full basket when a wallet contribution exists).
        confirm_order_payment(order_id, reference, provider_response=data, provider="paystack")
        return order.get("campus_id")

    elif payment_type == "event_ticket_payment":
        return _confirm_event_ticket_charge(db, metadata, reference, data, "paystack")

    elif payment_type == "marketplace_purchase":
        return _complete_marketplace_charge(db, metadata, reference, data, "paystack")

    elif payment_type == "wallet_topup" and not user_id:
        # A top-up reference without an owner used to fall through to `return None`, which
        # marked the delivery "processed" while nobody was credited. Fail loudly instead.
        raise ValueError(f"Wallet top-up {reference} has no user_id in its metadata")

    elif payment_type == "wallet_topup" and user_id:
        from app.services.wallet_payments import confirm_paystack_wallet_funding
        funded = confirm_paystack_wallet_funding(data, reference)
        if funded['payment_status'] != 'paid':
            raise ValueError('Wallet payment is not successful')
        amount_naira = funded['amount']
        campus_id = funded['campus_id']
        _fmt_amt = f"{amount_naira:,.0f}"
        try:
            send_notification(
                user_id=user_id,
                notif_type="wallet_funded_card",
                template_data={"amount": _fmt_amt},
                campus_id=campus_id,
            )
        except Exception as exc:
            # [D10] the wallet is already credited -- a notification failure must not turn this into a "failed" event
            current_app.logger.error("Post-payment notification failed for %s (payment already confirmed): %s", reference, exc)
        return campus_id

    elif not payment_type and authorization.get("channel") == "dedicated_nuban":
        # Incoming bank transfer to a customer's dedicated virtual account. Paystack reports these as `charge.success`
        # (authorization.channel == "dedicated_nuban"), NOT as `transfer.success` (that event is for payouts we send).
        # Until now they fell through to `return None`, so the event was marked "processed" but nobody was credited.
        return _credit_virtual_account_deposit(
            account_number=authorization.get("receiver_bank_account_number"),
            amount_naira=amount_naira,
            reference=reference,
            provider_response=data,
        )
    return None


def _handle_dva_assign(data: dict):
    """
    Handle dedicated virtual account assignment. Update or insert wallet record.
    """
    customer = data.get("customer", {})
    account = data.get("dedicated_account", {})
    user_email = customer.get("email")
    if not user_email:
        return None
    db = get_db()
    user_rows = db.table("profiles").select("id,campus_id").eq("email", user_email).limit(1).execute()
    if not user_rows:
        return None
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
    return campus_id


def _handle_transfer(data: dict):
    """Bank transfer credited to virtual account -> credit wallet (kept for providers/accounts that report deposits as transfer.success)."""
    reference = data.get("reference")
    amount_naira = data.get("amount", 0) / 100
    recipient = data.get("recipient") or {}
    account_number = (recipient.get("details") or {}).get("account_number")
    return _credit_virtual_account_deposit(account_number, amount_naira, reference)


def _credit_virtual_account_deposit(account_number, amount_naira, reference, provider_response=None):
    """
    Credit the wallet that owns `account_number` (a dedicated virtual account). Shared by the charge.success
    (dedicated_nuban) path and transfer.success. Raises ValueError for anything that cannot be credited, which
    marks the webhook event "failed" and alerts admins (paystack_webhook's except block does the alerting).
    Replay-safe: credit_wallet_atomic ignores a provider_reference it has already credited.
    """
    db = get_db()
    if not account_number:
        raise ValueError(f"Bank transfer webhook error: missing account_number for ref {reference}")
    if amount_naira <= 0:
        raise ValueError(f"Invalid bank transfer amount for ref {reference}")

    va_rows = db.table("virtual_accounts").select("user_id,campus_id").eq("account_number", str(account_number)).limit(1).execute()
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
        raise ValueError(f"Bank transfer webhook error: no virtual account found for account_number {account_number} (ref {reference})")

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
        provider_response=provider_response,
        campus_id=campus_id,
    )
    _fmt_amt = f"{amount_naira:,.0f}"
    try:
        send_notification(
            user_id=user_id,
            notif_type="wallet_funded_bank",
            template_data={"amount": _fmt_amt},
            campus_id=campus_id,
        )
    except Exception as exc:
        # [D10] the wallet is already credited -- a notification failure must not turn this into a "failed" event
        current_app.logger.error("Post-payment notification failed for %s (payment already confirmed): %s", reference, exc)
    return campus_id


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
    except Exception as exc:
        # This is the failure-reporting path: if it fails silently, a broken webhook
        # produces no alert at all and the first sign of trouble is a customer complaint.
        logger.error("webhook failure alert could not be sent (%s, ref %s): %s",
                     event_type, reference, exc)
