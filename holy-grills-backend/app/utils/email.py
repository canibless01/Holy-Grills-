"""
Application email dispatch with preferred provider and quota-only failover.
The caller receives False for an unavailable or uncertain outcome; no speculative retry.

Resend REST API: POST https://api.resend.com/emails
Auth: Authorization: Bearer <RESEND_API_KEY>
"""

import os
import requests
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

RESEND_BASE = "https://api.resend.com"

TEMPLATES = {
    "order_confirmed": {
        "subject": MSG.EMAIL_ORDER_CONFIRMED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your order #{d.get('order_id','')[:8].upper()} has been received and is heading to the kitchen.

Total: ₦{d.get('total', 0):,.0f}
Estimated delivery: {d.get('window_label', 'your selected window')}

Track your order in the app.

— {d.get('app_tagline', '')}
""",
    },
    "hp_earned": {
        "subject": MSG.EMAIL_HP_EARNED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You earned {d.get('hp', 0)} {d.get('currency', 'HP')} on your recent order. Keep ordering to build your {d.get('currency', 'HP')} balance and unlock rewards!

Your balance: {d.get('active_hp', 0)} {d.get('currency', 'HP')} active | {d.get('pending_hp', 0)} {d.get('currency', 'HP')} pending

— {d.get('app_tagline', '')}
""",
    },
    "tier_upgrade": {
        "subject": MSG.EMAIL_TIER_UPGRADE,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Congratulations — you've reached {d.get('tier_name', '')} tier!

Your new benefits:
{d.get('perks', '')}

Keep earning to maintain your status.

— {d.get('app_tagline', '')}
""",
    },
    "wallet_funded": {
        "subject": MSG.EMAIL_WALLET_FUNDED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your {d.get('app_name', '')} wallet has been credited with ₦{d.get('amount', 0):,.0f}.

New balance: ₦{d.get('new_balance', 0):,.0f}

— {d.get('app_tagline', '')}
""",
    },
    "password_reset": {
        "subject": MSG.EMAIL_PASSWORD_RESET,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

We received a request to reset your password. Click the link below:

{d.get('reset_link', '')}

This link expires in 1 hour. If you didn't request this, ignore this email.

— {d.get('app_tagline', '')}
""",
    },
    "birthday_bonus": {
        "subject": MSG.EMAIL_BIRTHDAY_BONUS,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Happy Birthday! As a gift, we've added {d.get('hp', 150)} {d.get('currency', 'HP')} to your account.

Head to the app and treat yourself on us!

— {d.get('app_tagline', '')}
""",
    },
    "referral_completed": {
        "subject": MSG.EMAIL_REFERRAL_COMPLETED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Great news — a friend you referred just placed their first order on {d.get('app_name', '')}.

You've earned {d.get('hp', 75)} {d.get('currency', 'HP')} (active, no monthly cap). Spend it on your next order!

— {d.get('app_tagline', '')}
""",
    },
    "abandoned_cart": {
        "subject": MSG.EMAIL_ABANDONED_CART,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You left some items in your cart. Come back and complete your order — your {d.get('currency', 'HP')} is waiting!

{d.get('items_summary', '')}

— {d.get('app_tagline', '')}
""",
    },
    "reward_redeemed": {
        "subject": MSG.EMAIL_REWARD_REDEEMED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You redeemed: {d.get('reward_name', '')} for {d.get('hp_spent', 0)} {d.get('currency', 'HP')}.

Our team will fulfil your reward within {d.get('fulfilment_time', '24 hours')}.

— {d.get('app_tagline', '')}
""",
    },
    "tier_grace_period": {
        "subject": MSG.EMAIL_TIER_GRACE,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your {d.get('currency', 'HP')} activity has dipped below the {d.get('tier_name', 'your tier')} threshold.
You have {d.get('grace_days', 7)} days to place an order and keep your tier status.

— {d.get('app_tagline', '')}
""",
    },
    "tier_dropped": {
        "subject": MSG.EMAIL_TIER_DROPPED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your grace period has ended and your tier has been updated.
Keep ordering to climb back up!

— {d.get('app_tagline', '')}
""",
    },
    "hp_expired": {
        "subject": MSG.EMAIL_HP_EXPIRED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

{d.get('amount', 0)} {d.get('currency', 'HP')} has decayed due to {d.get('inactivity_days', 120)} days of inactivity.
Place an order to protect your remaining balance!

— {d.get('app_tagline', '')}
""",
    },
    "monthly_birthday_report": {
        "subject": lambda d: f"🎂 Birthday Report — {d.get('month', 'This Month')} ({d.get('count', 0)} users)",
        "body": lambda d: f"""
Hi {d.get('name', 'Admin')},

Here are the {d.get('app_name', '')} users with birthdays in {d.get('month', 'this month')}:

{d.get('summary_text', 'No birthdays this month.')}

Total: {d.get('count', 0)} user{'s' if d.get('count', 0) != 1 else ''}

You can use this list to send birthday wishes, create flyers, or DM them directly.

— {d.get('app_tagline', '')}
""",
    },
    "event_tickets_export": {
        "subject": lambda d: f"Event Registrants — {d.get('event_title', 'Event')}",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Please find attached the registrant list for {d.get('event_title', 'your event')}.

Total registrants: {d.get('count', 0)}

{d.get('registrant_table', '')}

— {d.get('app_tagline', '')}
""",
    },
    "event_ticket_qr": {
        "subject": lambda d: f"🎟️ Your Ticket for {d.get('event_title', 'Event')}",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Here is your ticket for {d.get('event_title', '')}!

Date: {d.get('event_date', 'TBA')}
Location: {d.get('event_location', 'TBA')}
Ticket ID: {d.get('ticket_id', '')}

Please show your QR code at the door to check in.

Create an account to earn HP for this event!

— {d.get('app_tagline', '')}
""",
    },
    "squad_invite": {
        "subject": lambda d: f"You've been invited to join a squad order on {d.get('app_name', 'Holy Grills')}!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

{d.get('organizer', 'A friend')} added you to a squad order on {d.get('app_name', 'Holy Grills')}!

Join the squad order in the app to choose your meal and earn {d.get('currency', 'HP')}.

Sign up here to join and earn HP: {d.get('invite_link', '')}

— {d.get('app_tagline', '')}
""",
    },
    "guest_order_confirmed": {
        "subject": lambda d: f"Guest Order Confirmed — {d.get('app_name', 'Holy Grills')}",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your order #{d.get('order_id', '')} has been placed successfully!

Claim token: {d.get('claim_token', '')}

Create an account or log in with this email to claim your order and earn {d.get('currency', 'HP')}.

— {d.get('app_tagline', '')}
""",
    },
}


def _resend_api_key() -> str:
    """Return RESEND_API_KEY from env. Empty string if not configured."""
    return os.environ.get("RESEND_API_KEY", "")


import html as _html

def _build_html(name: str, body_text: str, app_tagline: str) -> str:
    """Wrap plain-text body in a minimal responsive HTML shell."""
    safe_name = _html.escape(str(name or "there"))
    safe_tagline = _html.escape(str(app_tagline or ""))
    body_html = _html.escape(body_text.strip()).replace("\n", "<br>")
    return (
        f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
        f"<p>Hi {safe_name},</p>"
        f"<p>{body_html}</p>"
        f"<br><p style='color:#888;font-size:12px'>— {safe_tagline}</p>"
        f"</body></html>"
    )


def send_email(to_email: str, to_name: str, template_key: str, data: dict = None, provider: str = None) -> bool:
    """
    Send a transactional email via whichever provider get_email_provider
    resolves to. Template resolution: email_templates DB row (admin-edited)
    takes precedence; falls back to the hardcoded TEMPLATES dict if no row
    exists for this template_key.
    """
    data = data or {}
    data.setdefault("name", to_name)
    data.setdefault("app_tagline", os.environ.get("APP_TAGLINE", "Holy Grills FUTA"))
    data.setdefault("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    data.setdefault("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))

    db_template = None
    try:
        from app.db import get_db
        db_template = get_db().table("email_templates").select("subject,body").eq("template_key", template_key).single().execute()
    except Exception:
        db_template = None

    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"  # leave unresolvable placeholders visible rather than raising

    if db_template:
        try:
            subject = db_template["subject"].format_map(_SafeDict(data))
            body_text = db_template["body"].format_map(_SafeDict(data))
        except Exception as e:
            logger.error("send_email: malformed admin template '%s': %s — falling back to hardcoded", template_key, e)
            db_template = None

    if not db_template:
        template = TEMPLATES.get(template_key)
        if not template:
            logger.warning("send_email: unknown template_key '%s'", template_key)
            return False
        subject_tpl = template["subject"]
        subject = subject_tpl(data) if callable(subject_tpl) else subject_tpl
        body_text = template["body"](data)

    _app_name = data.get("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    _currency = data.get("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))
    if isinstance(subject, str):
        subject = subject.replace("{platform}", _app_name).replace("{currency}", _currency)
    body_text = body_text.replace("{platform}", _app_name).replace("{currency}", _currency)

    html_body = _build_html(to_name or "there", body_text, data.get("app_tagline", ""))

    from app.services.notification_service import get_email_provider
    chosen = get_email_provider(scope="transactional", override=provider)
    return send_email_routed(to_email, to_name, subject, html_body, provider=chosen)


def _email_quota_rejection(response):
    """Only an explicit provider refusal may switch transports safely."""
    if response.status_code == 429:
        return True
    if response.status_code not in (400, 403):
        return False
    try:
        detail = response.json()
    except (ValueError, TypeError):
        return False
    if not isinstance(detail, dict):
        return False
    name = str(detail.get("name") or detail.get("code") or "").lower()
    if name in {"daily_quota_exceeded", "monthly_quota_exceeded", "quota_exceeded", "rate_limit_exceeded"}:
        return True
    # OneSignal reports its monthly email allowance in the errors field.
    errors = detail.get("errors")
    if isinstance(errors, str):
        errors = [errors]
    return isinstance(errors, list) and any(
        isinstance(value, str) and "email" in value.lower()
        and "limit" in value.lower() and "exceed" in value.lower()
        and ("monthly" in value.lower() or "daily" in value.lower())
        for value in errors)


def _email_attempt(provider, to_email, to_name, subject, html_body, headers=None):
    """Return (accepted, definitely_quota_rejected). Never retry ambiguity."""
    try:
        if provider == "onesignal":
            from app.services.notification_service import _get_onesignal_creds, _onesignal_email_post, _ONESIGNAL_BASE
            app_id, api_key = _get_onesignal_creds()
            if not app_id or not api_key:
                return False, False
            # Custom RFC unsubscribe headers cannot safely be translated to an
            # undocumented provider field. Preserve the caller's Resend path.
            if headers:
                return False, False
            payload = {"app_id": app_id, "target_channel": "email", "include_email_tokens": [to_email],
                       "email_subject": subject, "email_body": html_body}
            response = _onesignal_email_post(f"{_ONESIGNAL_BASE}/notifications",
                                      headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
                                      payload=payload)
            accepted = response.status_code in (200, 202)
            if accepted:
                try:
                    detail = response.json()
                    accepted = not (isinstance(detail, dict) and detail.get("errors"))
                except (ValueError, TypeError):
                    accepted = False
        else:
            api_key = _resend_api_key()
            if not api_key:
                return False, False
            from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
            from_name = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")
            payload = {"from": f"{from_name} <{from_email}>", "to": [to_email], "subject": subject, "html": html_body}
            if headers:
                payload["headers"] = dict(headers)
            response = requests.post(f"{RESEND_BASE}/emails",
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                                     json=payload, timeout=10)
            accepted = response.status_code in (200, 201)
        if accepted:
            return True, False
        quota = _email_quota_rejection(response)
        logger.warning("Email provider %s rejected delivery with status %s (quota=%s)", provider, response.status_code, quota)
        return False, quota
    except Exception as exc:
        # A timeout/connection reset may follow provider acceptance. A second
        # transport here could deliver the same message twice.
        logger.warning("Email provider %s outcome unavailable: %s", provider, type(exc).__name__)
        return False, False


def send_email_routed(to_email, to_name, subject, html_body, *, provider="resend", headers=None):
    """One preferred attempt, then one alternate only after a quota refusal.

    No counters, global configuration changes or speculative timeout retries.
    This is application email routing; Supabase Auth SMTP is independent.
    """
    chosen = "onesignal" if provider == "onesignal" else "resend"
    if headers:
        chosen = "resend"  # Retain explicit unsubscribe/custom headers.
    accepted, quota = _email_attempt(chosen, to_email, to_name, subject, html_body, headers)
    if accepted:
        return True
    if not quota or headers:
        return False
    alternate = "resend" if chosen == "onesignal" else "onesignal"
    accepted, _ = _email_attempt(alternate, to_email, to_name, subject, html_body)
    return accepted


def send_email_raw(to_email: str, to_name: str, subject: str, html_body: str, headers: dict = None) -> bool:
    """Raw transactional email prefers Resend, with quota-only fallback."""
    return send_email_routed(to_email, to_name, subject, html_body, provider="resend", headers=headers)


def get_user_email_and_name(user_id: str) -> tuple:
    """Fetch user email + display name (nickname-first) from profiles."""
    from app.db import get_db
    from app.services.squad_service import resolve_display_name
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("id,nickname,full_name,email,department,campus_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if profile:
            return profile.get("email", ""), resolve_display_name(profile=profile)
        return "", ""
    except Exception:
        return "", ""


def send_qr_ticket_email(email: str, name: str, event_title: str, ticket_id: str, event_id: str, event_date: str = "", event_location: str = "") -> bool:
    """
    Send QR ticket email to guest or registered user.
    Generates QR code payload (hg-event:{event_id}:{ticket_id}) locally as base64 PNG.
    Does NOT leak ticket IDs to third-party QR generation APIs.
    """
    qr_payload = f"hg-event:{event_id}:{ticket_id}"

    try:
        import qrcode
        import io, base64
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        qr_img_tag = f'<img src="data:image/png;base64,{img_str}" alt="QR Ticket Code" style="width:200px;height:200px;display:block;margin:15px 0;" />'
    except Exception as e:
        logger.error("send_qr_ticket_email: Failed to generate local base64 QR code for ticket %s: %s", ticket_id, e)
        # Fail closed instead of leaking ticket_id to third-party external server
        return False

    safe_title = _html.escape(str(event_title or ""))
    safe_name = _html.escape(str(name or "there"))
    safe_date = _html.escape(str(event_date or "TBA"))
    safe_location = _html.escape(str(event_location or "TBA"))
    safe_ticket_id = _html.escape(str(ticket_id or ""))
    safe_email = _html.escape(str(email or ""))

    app_tagline = _html.escape(os.environ.get("APP_TAGLINE", "Holy Grills FUTA"))
    subject = f"🎟️ Your Ticket for {event_title}"

    html_body = (
        f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
        f"<h2>🎟️ Your Ticket for {safe_title}</h2>"
        f"<p>Hi {safe_name},</p>"
        f"<p>Thank you for registering! Here are your official ticket details:</p>"
        f"<ul>"
        f"<li><strong>Event:</strong> {safe_title}</li>"
        f"<li><strong>Date:</strong> {safe_date}</li>"
        f"<li><strong>Location:</strong> {safe_location}</li>"
        f"<li><strong>Ticket ID:</strong> <code>{safe_ticket_id}</code></li>"
        f"</ul>"
        f"<p>Present this QR code at the door for check-in:</p>"
        f"{qr_img_tag}"
        f"<div style='background-color:#f0f8ff;border-left:4px solid #0080ff;padding:12px;margin:20px 0;'>"
        f"<strong>Earn Rewards!</strong> Create an account with {safe_email} to earn HP for this event and unlock exclusive perks!"
        f"</div>"
        f"<br><p style='color:#888;font-size:12px'>— {app_tagline}</p>"
        f"</body></html>"
    )

    return send_email_raw(to_email=email, to_name=name, subject=subject, html_body=html_body)
