"""
Email dispatch via OneSignal. All calls are fire-and-forget.
Falls back gracefully if OneSignal is not configured.

OneSignal REST API: POST https://api.onesignal.com/notifications
Auth: Authorization: Key <ONESIGNAL_API_KEY>
"""

import os
import requests
from flask import current_app


ONESIGNAL_BASE = os.environ.get("ONESIGNAL_BASE_URL", "https://api.onesignal.com")

TEMPLATES = {
    "order_confirmed": {
        "subject": "Your Holy Grills order is confirmed!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your order #{d.get('order_id','')[:8].upper()} has been received and is heading to the kitchen.

Total: ₦{d.get('total', 0):,.0f}
Estimated delivery: {d.get('window_label', 'your selected window')}

Track your order in the app.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "hp_earned": {
        "subject": "You just earned Holy Points!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You earned {d.get('hp', 0)} HP on your recent order. Keep ordering to build your balance and unlock rewards!

Your balance: {d.get('active_hp', 0)} HP active | {d.get('pending_hp', 0)} HP pending

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "tier_upgrade": {
        "subject": "You levelled up on Holy Grills!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Congratulations — you've reached {d.get('tier_name', '')} tier!

Your new benefits:
{d.get('perks', '')}

Keep earning to maintain your status.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "wallet_funded": {
        "subject": "Wallet funded successfully",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your Holy Grills wallet has been credited with ₦{d.get('amount', 0):,.0f}.

New balance: ₦{d.get('new_balance', 0):,.0f}

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "password_reset": {
        "subject": "Reset your Holy Grills password",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

We received a request to reset your password. Click the link below:

{d.get('reset_link', '')}

This link expires in 1 hour. If you didn't request this, ignore this email.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "birthday_bonus": {
        "subject": "Happy Birthday from Holy Grills!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Happy Birthday! As a gift, we've added {d.get('hp', 150)} HP to your account.

Your HP is valid for 30 days — head to the app and treat yourself!

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "referral_completed": {
        "subject": "Your referral earned you HP!",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Great news — a friend you referred just placed their first order on Holy Grills.

You've earned {d.get('hp', 75)} HP (active). Spend it on your next order!

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "abandoned_cart": {
        "subject": "Your cart is waiting for you",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You left some items in your cart. Come back and complete your order — your HP is waiting!

{d.get('items_summary', '')}

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "reward_redeemed": {
        "subject": "Reward redemption confirmed",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You redeemed: {d.get('reward_name', '')} for {d.get('hp_spent', 0)} HP.

Our team will fulfil your reward within {d.get('fulfilment_time', '24 hours')}.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "tier_grace_period": {
        "subject": "Your tier grace period has started",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your HP activity has dipped below the {d.get('tier_name', 'your tier')} threshold.
You have {d.get('grace_days', 7)} days to place an order and keep your tier status.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "tier_dropped": {
        "subject": "Your tier has changed",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your grace period has ended and your tier has been updated.
Keep ordering to climb back up!

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "hp_expired": {
        "subject": "Some of your HP has expired",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

{d.get('amount', 0)} HP has expired due to {d.get('inactivity_days', 90)} days of inactivity.
Place an order to protect your remaining balance!

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
    "monthly_birthday_report": {
        "subject": lambda d: f"🎂 Birthday Report — {d.get('month', 'This Month')} ({d.get('count', 0)} users)",
        "body": lambda d: f"""
Hi {d.get('name', 'Admin')},

Here are the Holy Grills users with birthdays in {d.get('month', 'this month')}:

{d.get('summary_text', 'No birthdays this month.')}

Total: {d.get('count', 0)} user{'s' if d.get('count', 0) != 1 else ''}

You can use this list to send birthday wishes, create flyers, or DM them directly.

— {d.get('app_tagline', 'Holy Grills FUTA')}
""",
    },
}


def send_email(to_email: str, to_name: str, template_key: str, data: dict = None) -> bool:
    """
    Send a transactional email via OneSignal.
    Returns True on success, False on failure (never raises).
    """
    app_id = os.environ.get("ONESIGNAL_APP_ID", "")
    api_key = os.environ.get("ONESIGNAL_API_KEY", "")

    if not app_id or not api_key:
        return False

    template = TEMPLATES.get(template_key)
    if not template:
        return False

    data = data or {}
    data.setdefault("name", to_name)
    data.setdefault("app_tagline", os.environ.get("APP_TAGLINE", "Holy Grills FUTA"))

    from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    from_name = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    subject_tpl = template["subject"]
    subject = subject_tpl(data) if callable(subject_tpl) else subject_tpl

    body_text = template["body"](data)
    body_html = body_text.replace("\n", "<br>")

    payload = {
        "app_id": app_id,
        "include_email_tokens": [to_email],
        "email_subject": subject,
        "email_body": (
            f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
            f"<p>{body_html}</p>"
            f"</body></html>"
        ),
        "email_from_name": from_name,
        "email_from_address": from_email,
    }

    try:
        resp = requests.post(
            f"{ONESIGNAL_BASE}/notifications",
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        return resp.status_code in (200, 202)
    except Exception:
        return False


def get_user_email_and_name(user_id: str) -> tuple:
    """Fetch user email + name from Supabase profiles table."""
    from app.db import get_db
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("full_name,email")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if profile:
            return profile.get("email", ""), profile.get("full_name", "")
        return "", ""
    except Exception:
        return "", ""
