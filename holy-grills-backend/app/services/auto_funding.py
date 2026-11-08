"""Consented, fixed-amount wallet funding. Never retry a money POST.

Database receipts own dispatch, stop and credit transitions. Unknown outcomes
are reconciled by the original reference; reusable card credentials stay private.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from uuid import UUID
from urllib.parse import quote

import requests
from flask import current_app

from app.db import get_db
from app.services.payment_service import PAYSTACK_BASE, _paystack_headers
from app.utils.settings import setting_or_config

CONSENT_VERSION = "wallet-auto-funding-v1"
PUBLIC_FIELDS = (
    "id", "amount_kobo", "interval_days", "stop_after", "end_at", "state",
    "successful_payments", "total_credited_kobo", "next_due_at", "created_at",
    "stopped_at", "last_issue", "card_label", "setup_reference", "checkout_url",
    "in_flight", "attempts",
)


class FundingError(ValueError):
    pass


def rpc(action, *, user_id=None, plan_id=None, data=None):
    return get_db().rpc("hg_wallet_auto_funding", {
        "p_action": action, "p_user_id": user_id, "p_id": plan_id, "p_data": data or {},
    })


def public_plan(plan):
    return {key: plan.get(key) for key in PUBLIC_FIELDS if key in plan}


def limits():
    minimum = setting_or_config(get_db(), "wallet_min_card_topup",
                                current_app.config.get("WALLET_MIN_CARD_TOPUP", 100), minimum=100)
    return {"minimum_amount": minimum, "maximum_amount": 1000000,
            "maximum_interval_days": 365, "fee_payer": "holy_grills", "consent_version": CONSENT_VERSION,
            "enabled": current_app.config.get("WALLET_AUTO_FUNDING_ENABLED", True)}


def validate_terms(body, minimum):
    try:
        request_id = str(UUID(str(body.get("request_id", ""))))
        raw_amount = body.get("amount")
        if isinstance(raw_amount, bool):
            raise ValueError()
        amount = Decimal(str(raw_amount))
        if not amount.is_finite() or amount < Decimal(str(minimum)) or amount > 1000000 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError()
        interval = body.get("interval_days")
        if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 365:
            raise ValueError()
        count = body.get("stop_after")
        end_date = body.get("end_date")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 3650):
            raise ValueError()
        if count is not None and end_date:
            raise ValueError()
        end_at = None
        if end_date:
            day = date.fromisoformat(end_date)
            # Inclusive date in Nigeria; no browser timezone ambiguity.
            end = datetime.combine(day + timedelta(days=1), time(), timezone(timedelta(hours=1)))
            if end <= datetime.now(timezone.utc) or day > date.today() + timedelta(days=3650):
                raise ValueError()
            end_at = end.isoformat()
        if body.get("consent") is not True or body.get("consent_version") != CONSENT_VERSION:
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise FundingError("Choose a valid amount, frequency and stop option, and accept automatic funding.") from None
    return request_id, {"amount_kobo": int(amount * 100), "interval_days": interval,
                        "stop_after": count, "end_at": end_at, "consent_version": CONSENT_VERSION}


def _provider(method, path, payload=None):
    """Call Paystack once, retaining its safe diagnostic without logging secrets.

    In particular, do not call raise_for_status() before reading the JSON body:
    Paystack returns the useful initialization error in that body. Money POSTs
    deliberately have no retry decorator or session retry adapter.
    """
    response = requests.request(method, f"{PAYSTACK_BASE}{path}", headers=_paystack_headers(),
                                json=payload if method == "POST" else None, timeout=10)
    try:
        result = response.json()
    except (ValueError, TypeError):
        result = None
    if not isinstance(result, dict):
        current_app.logger.warning("Paystack returned a non-JSON response (HTTP %s).", response.status_code)
        raise FundingError("Paystack could not confirm the request. Please try again.") from None
    if response.status_code >= 400 or result.get("status") is not True:
        message = result.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "Paystack could not confirm the request. Please try again."
        # Never echo a charge-authorization error: unlike setup/verify errors,
        # its context includes a reusable credential. The reference is already
        # durable, so reconciliation remains safe without provider detail here.
        if path == "/transaction/charge_authorization":
            current_app.logger.warning("Paystack recurring charge was rejected (HTTP %s); existing reference awaits verification.", response.status_code)
            raise FundingError("The automatic payment needs verification; no new charge will be attempted.")
        # Setup/verify provider messages contain no reusable card credential.
        # Bound/control-clean them before returning them to the UI or logging.
        message = " ".join(message.split())[:240]
        current_app.logger.warning("Paystack request rejected (HTTP %s): %s", response.status_code, message)
        raise FundingError(message)
    if not isinstance(result.get("data"), dict):
        raise FundingError("Paystack returned an incomplete response. Please try again.")
    return result["data"]


def _mark_setup_failed(user_id, plan_id):
    """Best-effort state update; never mask the original initialization error."""
    try:
        rpc("setup_failed", user_id=user_id, plan_id=plan_id)
    except Exception:
        current_app.logger.warning("Automatic funding setup failure could not be recorded for plan %s.", plan_id)


def create_plan(user_id, body):
    if not current_app.config.get("PAYSTACK_SECRET_KEY"):
        raise FundingError("Card payments are unavailable. Try again later.")
    if not current_app.config.get("WALLET_AUTO_FUNDING_ENABLED", True):
        raise FundingError("Automatic funding is paused. Existing payments are still being checked.")
    plan_id, terms = validate_terms(body, limits()["minimum_amount"])
    result = rpc("create", user_id=user_id, plan_id=plan_id, data=terms)
    plan = result["plan"]
    if result.get("created"):
        try:
            root = current_app.config["FRONTEND_URL"].split(",")[0].rstrip("/")
            checkout = _provider("POST", "/transaction/initialize", {
                "email": plan["authorization_email"], "amount": plan["amount_kobo"],
                "reference": plan["setup_reference"], "currency": "NGN",
                # Match ordinary wallet initialization: Paystack uses the
                # integration's working channels. Verification below still
                # activates future debits only for a reusable card authorization.
                "callback_url": f"{root}/wallet?auto_funding={plan_id}",
                "metadata": {"type": "wallet_auto_funding", "plan_id": plan_id},
            })
            if checkout.get("reference") != plan["setup_reference"]:
                raise FundingError("The payment reference could not be confirmed.")
            checkout_url = checkout.get("authorization_url")
            if not isinstance(checkout_url, str) or not checkout_url.startswith("https://checkout.paystack.com/"):
                raise FundingError("Paystack did not return a valid checkout link. Please try again.")
            plan = rpc("checkout", user_id=user_id, plan_id=plan_id,
                       data={"checkout_url": checkout_url})
        except FundingError:
            _mark_setup_failed(user_id, plan_id)
            raise
        except requests.RequestException:
            _mark_setup_failed(user_id, plan_id)
            current_app.logger.warning("Paystack initialization was unreachable for automatic funding plan %s.", plan_id)
            raise FundingError("Paystack could not be reached. Check the plan status before trying again.") from None
        except Exception:
            _mark_setup_failed(user_id, plan_id)
            current_app.logger.exception("Automatic funding initialization failed for plan %s.", plan_id)
            raise FundingError("Funding setup could not be completed. Check its status before trying a new plan.") from None
    return public_plan(plan)


def confirm_payment(data, *, expected_user_id=None, plan_id=None):
    """Only call with a verified provider response or a signature-checked webhook."""
    reference = data.get("reference")
    if not isinstance(reference, str) or not reference.startswith("HG-AUTO-"):
        raise FundingError("Unknown automatic funding payment.")
    if data.get("status") != "success":
        return {"payment_status": "pending"}
    amount = data.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or data.get("currency") != "NGN":
        raise FundingError("Payment amount or currency does not match.")
    requested = data.get("requested_amount")
    if requested is not None and requested != amount:
        raise FundingError("Payment amount does not match.")
    auth = data.get("authorization") or {}
    if not isinstance(auth, dict):
        auth = {}
    safe_auth = {key: auth.get(key) for key in ("authorization_code", "reusable", "signature", "last4", "brand", "channel", "exp_month", "exp_year")}
    result = rpc("confirm", user_id=expected_user_id, plan_id=plan_id, data={
        "reference": reference, "amount_kobo": amount, "currency": "NGN",
        "authorization": safe_auth, "fees_kobo": data.get("fees"),
    })
    try:
        complete_effects(result)
    except Exception:
        # Cash is committed. The bounded sweep retries effects using stable IDs.
        current_app.logger.warning("Automatic funding receipt effects need recovery: %s", result["attempt_id"])
    return {"payment_status": "paid", "plan": public_plan(result["plan"]), "campus_id": result.get("campus_id")}


def complete_effects(receipt):
    from app.services.wallet_service import apply_wallet_funding_rewards
    from app.services.notification_service import send_notification
    # Use the committed ledger campus, including a campus change while a card
    # payment was already processing. The paid money is never discarded.
    transaction = get_db().table("wallet_transactions").select("id,user_id,amount,campus_id,provider_reference").eq(
        "id", receipt["transaction_id"]).single().execute()
    if not transaction or transaction.get("user_id") != receipt["user_id"] or transaction.get("provider_reference") != receipt["reference"]:
        raise FundingError("Wallet funding receipt is unavailable.")
    campus_id = transaction.get("campus_id")
    apply_wallet_funding_rewards(receipt["user_id"], receipt["amount_kobo"] / 100,
                                 receipt["transaction_id"], "topup", campus_id, strict=True)
    send_notification(user_id=receipt["user_id"], notif_type="wallet_funded_card",
                      template_data={"amount": f'{receipt["amount_kobo"] / 100:,.2f}'},
                      reference_id=receipt["attempt_id"], reference_type="wallet_auto_funding",
                      campus_id=campus_id, strict=True)
    rpc("effects_done", data={"reference": receipt["reference"]})


def verify_setup(user_id, plan_id, reference):
    plan = rpc("get", user_id=user_id, plan_id=plan_id)
    if reference != plan["setup_reference"]:
        raise FundingError("This payment does not belong to this funding plan.")
    data = _provider("GET", f"/transaction/verify/{quote(reference, safe='')}")
    if data.get("status") in ("failed", "abandoned", "reversed"):
        rpc("failed", user_id=user_id, plan_id=plan_id, data={"reference": reference})
        return {"payment_status": "failed", "plan": public_plan(rpc("get", user_id=user_id, plan_id=plan_id))}
    return confirm_payment(data, expected_user_id=user_id, plan_id=plan_id)


def sweep(limit=20, budget_seconds=45):
    """One bounded scan for all members; no per-member cron or catch-up bursts."""
    deadline = monotonic() + budget_seconds
    limit = min(max(int(limit), 1), 20)
    items = rpc("due", data={"limit": limit}) or []
    counts = {"checked": 0, "dispatched": 0, "unavailable": 0}
    for item in items:
        if monotonic() >= deadline:
            break
        try:
            if item["action"] == "effects":
                complete_effects(item)
            elif item["action"] == "verify":
                if not current_app.config.get("PAYSTACK_SECRET_KEY"):
                    counts["unavailable"] += 1
                    continue
                data = _provider("GET", f'/transaction/verify/{quote(item["reference"], safe="")}')
                if data.get("status") == "success":
                    confirm_payment(data)
                elif data.get("status") in ("failed", "abandoned", "reversed"):
                    rpc("failed", data={"reference": item["reference"]})
            else:
                if not current_app.config.get("WALLET_AUTO_FUNDING_ENABLED", True) or not current_app.config.get("PAYSTACK_SECRET_KEY"):
                    continue
                dispatch = rpc("dispatch", plan_id=item["id"])
                if not dispatch:
                    continue
                counts["dispatched"] += 1
                data = _provider("POST", "/transaction/charge_authorization", {
                    "authorization_code": dispatch["authorization_code"], "email": dispatch["authorization_email"],
                    "amount": dispatch["amount_kobo"], "currency": "NGN", "reference": dispatch["reference"],
                    "metadata": {"type": "wallet_auto_funding", "plan_id": item["id"]},
                })
                # POST output can indicate authentication/processing. Only a
                # provider verification or signed webhook can commit cash.
                if data.get("reference") != dispatch["reference"]:
                    raise FundingError("Payment reference could not be confirmed.")
            counts["checked"] += 1
        except Exception:
            counts["unavailable"] += 1
            current_app.logger.warning("Automatic funding will reconcile its existing receipt; no charge retry.")
    if monotonic() < deadline:
        try:
            send_attention_notices(min(5, limit), deadline)
        except Exception:
            current_app.logger.warning("Automatic funding attention scan awaits recovery.")
    return counts


def send_attention_notices(limit=5, deadline=None):
    from app.services.notification_service import send_notification
    db = get_db()
    notices = db.rpc("hg_wallet_funding_attention", {"p_action": "claim", "p_limit": limit}) or []
    for notice in notices:
        if deadline is not None and monotonic() >= deadline:
            break
        try:
            send_notification(user_id=notice["user_id"], notif_type="wallet_auto_funding_attention",
                title="Automatic funding needs attention",
                body="Your automatic wallet contributions are paused. Check your plan before starting another payment. Money already funded remains available to spend.",
                action_url="/wallet?auto_funding=1", reference_id=notice["id"], reference_type="wallet_auto_funding",
                strict=True)
            db.rpc("hg_wallet_funding_attention", {"p_action": "done", "p_id": notice["id"]})
        except Exception:
            current_app.logger.warning("Automatic funding attention notice awaits recovery: %s", notice["id"])
