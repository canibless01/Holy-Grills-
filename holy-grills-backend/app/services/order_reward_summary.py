"""Minimal customer reward receipt, called only after order-read authorization."""
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)


def food_hp_reward_summary(db, order):
    if not order.get('user_id'):
        return None
    try:
        logs = (db.table('order_status_logs').select('metadata').eq('order_id', order['id'])
                .order('created_at').limit(50).execute()) or []
        plan = next((r['metadata']['hp_bonus_plan'] for r in logs
                     if isinstance(r.get('metadata'), dict) and 'hp_bonus_plan' in r['metadata']), None)
        if plan is None or plan.get('source') == 'none':
            return None
        if plan.get('source') != 'spin' or not plan.get('receipt_id'):
            return {'status': 'unavailable'}
        receipt = (db.table('exclusive_spin_fulfillments').select('prize_name,status,applied_order_id')
                   .eq('id', plan['receipt_id']).eq('user_id', order['user_id']).single().execute())
        if not receipt:
            return {'status': 'unavailable'}
        if receipt.get('applied_order_id') == order['id'] and receipt['status'] in ('pending', 'fulfilled'):
            status = 'applied' if receipt['status'] == 'fulfilled' else 'reserved'
        else:
            status = 'released'
        return {'status': status, 'name': receipt.get('prize_name') or MSG.CHECKOUT_HP_REWARD_NAME,
                'multiplier': plan['multiplier']}
    except Exception:
        logger.exception('Order reward receipt unavailable for %s', order['id'])
        return {'status': 'unavailable'}
