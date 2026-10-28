"""Expiry applies at reservation, never retrospectively to an attached order."""
from datetime import datetime, timezone
from app.messages import MSG


def available(receipt):
    expiry = (receipt.get('result_snapshot') or {}).get('expires_at')
    if not expiry: return True
    try:
        stamp = datetime.fromisoformat(str(expiry).replace('Z', '+00:00'))
        if stamp.tzinfo is None: raise ValueError()
        return stamp > datetime.now(timezone.utc)
    except (TypeError, ValueError): raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
