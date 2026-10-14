"""Read-only delivery offers; admission commits their claim with the payment."""
from decimal import Decimal, ROUND_HALF_UP
from app.db import get_db
from app.messages import MSG
from app.services.tier_service import resolve_perk
from app.utils.tz import today_wat


def _money(value):
    amount = Decimal(str(value or 0))
    if not amount.is_finite() or amount < 0:
        raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def quote_delivery_benefit(user_id, campus_id, delivery_fee, is_squad_order, *, db=None):
    fee = _money(delivery_fee)
    plan = {'source': 'none', 'original_fee': float(fee), 'discount': 0}
    if not user_id or fee == 0:
        return plan
    db = db or get_db()
    profile = db.table('profiles').select('id,is_active,campus_id,current_tier_id,next_order_free_delivery_cap').eq('id', user_id).single().execute()
    if not profile or not profile.get('is_active') or profile.get('campus_id') != campus_id:
        raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
    month = today_wat().strftime('%Y-%m')
    # A fully free monthly delivery preserves the customer's separate spin credit.
    monthly_enabled = resolve_perk(user_id, 'monthly_free_delivery', strict=True, db=db) if not is_squad_order else False
    if not isinstance(monthly_enabled, (bool, int, float)) or monthly_enabled not in (0, 1):
        raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
    if monthly_enabled:
        used = db.table('tier_monthly_perk_usage').select('id').eq('user_id', user_id).eq('month', month).eq('perk_key', 'monthly_free_delivery').limit(1).execute()
        if not used:
            return {**plan, 'source': 'monthly', 'discount': float(fee), 'month': month,
                    'tier_id': profile.get('current_tier_id')}
    legacy_cap = _money(profile.get('next_order_free_delivery_cap'))
    if legacy_cap > 0:
        return {**plan, 'source': 'legacy_spin', 'cap': float(legacy_cap),
                'discount': float(min(fee, legacy_cap))}
    rows = (db.table('exclusive_spin_fulfillments').select('id,result_snapshot')
            .eq('user_id', user_id).eq('campus_id', campus_id).eq('status', 'pending')
            .eq('result_snapshot->>prize_type', 'free_delivery').is_('applied_order_id', 'null')
            .order('created_at').order('id').limit(1).execute()) or []
    if rows:
        receipt = rows[0]
        cap = _money((receipt.get('result_snapshot') or {}).get('reward_config', {}).get('cap'))
        if cap <= 0:
            raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
        return {**plan, 'source': 'spin', 'receipt_id': receipt['id'], 'cap': float(cap),
                'discount': float(min(fee, cap))}
    return plan
