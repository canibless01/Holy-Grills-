"""Order-specific delivery contact without mutating the account profile."""
import re
from app.messages import MSG


def normalize_order_phone(value):
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError(MSG.ORDER_CONTACT_PHONE_INVALID)
    phone = re.sub(r'[\s()\-]', '', value)
    if re.fullmatch(r'0[789]\d{9}', phone):
        return '+234' + phone[1:]
    if re.fullmatch(r'\+?234[789]\d{9}', phone):
        return '+' + phone.lstrip('+')
    raise ValueError(MSG.ORDER_CONTACT_PHONE_INVALID)


def resolve_order_phone(db, user_id, payload, *, quote_only=False):
    if quote_only:
        return None  # Optional confirmation must not prevent pricing an unfinished checkout.
    if 'contact_phone' in payload:
        return normalize_order_phone(payload['contact_phone'])
    phone = payload.get('guest_phone')
    if user_id:
        profile = db.table('profiles').select('phone').eq('id', user_id).single().execute() or {}
        phone = profile.get('phone') or phone
    return normalize_order_phone(phone)


def order_call_phone(order, profile_phone=None):
    snapshot = order.get('delivery_address_snapshot')
    if isinstance(snapshot, dict) and snapshot.get('contact_phone'):
        return normalize_order_phone(snapshot['contact_phone'])
    # Historical orders have no contact snapshot; retain their original fallback.
    return profile_phone or order.get('guest_phone')
