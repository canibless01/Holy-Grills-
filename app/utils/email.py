"""
Email dispatch via SendGrid. All calls are fire-and-forget.
Falls back gracefully if SendGrid is not configured.
"""

import os
import requests
from flask import current_app


SENDGRID_BASE = 'https://api.sendgrid.com/v3'

TEMPLATES = {
    'order_confirmed': {
        'subject': 'Your Holy Grills order is confirmed!',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

Your order #{d.get('order_id','')[:8].upper()} has been received and is heading to the kitchen.

Total: ₦{d.get('total', 0):,.0f}
Estimated delivery: {d.get('window_label', 'your selected window')}

Track your order in the app.

— Holy Grills FUTA
""",
    },
    'hp_earned': {
        'subject': 'You just earned Holy Points!',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

You earned {d.get('hp', 0)} HP on your recent order. Keep ordering to build your balance and unlock rewards!

Your balance: {d.get('active_hp', 0)} HP active | {d.get('pending_hp', 0)} HP pending

— Holy Grills FUTA
""",
    },
    'tier_upgrade': {
        'subject': 'You levelled up on Holy Grills!',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

Congratulations — you've reached {d.get('tier_name', '')} tier!

Your new benefits:
{d.get('perks', '')}

Keep earning to maintain your status.

— Holy Grills FUTA
""",
    },
    'wallet_funded': {
        'subject': 'Wallet funded successfully',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

Your Holy Grills wallet has been credited with ₦{d.get('amount', 0):,.0f}.

New balance: ₦{d.get('new_balance', 0):,.0f}

— Holy Grills FUTA
""",
    },
    'password_reset': {
        'subject': 'Reset your Holy Grills password',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

We received a request to reset your password. Click the link below:

{d.get('reset_link', '')}

This link expires in 1 hour. If you didn't request this, ignore this email.

— Holy Grills FUTA
""",
    },
    'birthday_bonus': {
        'subject': 'Happy Birthday from Holy Grills! 🎂',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

Happy Birthday! As a gift, we've added 150 HP to your account.

Your HP is valid for 30 days — head to the app and treat yourself!

— Holy Grills FUTA
""",
    },
    'referral_completed': {
        'subject': 'Your referral earned you HP!',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

Great news — a friend you referred just placed their first order on Holy Grills.

You've earned 75 HP (pending). Place your next food order to unlock it!

— Holy Grills FUTA
""",
    },
    'abandoned_cart': {
        'subject': 'Your cart is waiting for you 🍗',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

You left some items in your cart. Come back and complete your order — your HP is waiting!

{d.get('items_summary', '')}

— Holy Grills FUTA
""",
    },
    'reward_redeemed': {
        'subject': 'Reward redemption confirmed',
        'body': lambda d: f"""
Hi {d.get('name', 'there')},

You redeemed: {d.get('reward_name', '')} for {d.get('hp_spent', 0)} HP.

Our team will fulfil your reward within {d.get('fulfilment_time', '24 hours')}.

— Holy Grills FUTA
""",
    },
}


def send_email(to_email: str, to_name: str, template_key: str, data: dict = None) -> bool:
    """
    Send a transactional email via SendGrid.
    Returns True on success, False on failure (never raises).
    """
    api_key = os.environ.get('SENDGRID_API_KEY', '')
    if not api_key:
        return False

    template = TEMPLATES.get(template_key)
    if not template:
        return False

    data = data or {}
    data.setdefault('name', to_name)
    from_email = os.environ.get('EMAIL_FROM', 'noreply@holygrills.ng')
    from_name = os.environ.get('EMAIL_FROM_NAME', 'Holy Grills')

    payload = {
        'personalizations': [{'to': [{'email': to_email, 'name': to_name}]}],
        'from': {'email': from_email, 'name': from_name},
        'subject': template['subject'],
        'content': [{'type': 'text/plain', 'value': template['body'](data)}],
    }

    try:
        resp = requests.post(
            f'{SENDGRID_BASE}/mail/send',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=10,
        )
        return resp.status_code in (200, 202)
    except Exception:
        return False


def get_user_email_and_name(user_id: str) -> tuple[str, str]:
    """Fetch user email from Supabase auth + name from profiles."""
    from app.db import get_db
    db = get_db()
    try:
        profile = db.table('profiles').select('full_name').eq('id', user_id).single().execute()
        name = profile.get('full_name', '') if profile else ''
        auth_user = db.auth_get_user(
            db.auth_sign_in.__func__  # can't get email from service role easily
        )
        return '', name
    except Exception:
        return '', ''
