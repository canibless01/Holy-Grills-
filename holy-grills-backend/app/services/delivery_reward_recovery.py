"""Complete the financial part of delivery rewards from durable order receipts."""
import math
from flask import current_app
from app.db import get_db
from app.messages import MSG
from app.utils.settings import get_validated_setting


def complete_delivery_financial_rewards(order, food_spend=None):
    db = get_db()
    order_id = order['id']
    # Reuse snapshotted terms on retry; do not re-price an earned grant.
    rows = (db.table('order_status_logs').select('metadata').eq('order_id', order_id)
            .order('created_at').execute()) or []
    receipt = next((row['metadata']['delivery_reward_recovery'] for row in rows
                    if isinstance(row.get('metadata'), dict) and 'delivery_reward_recovery' in row['metadata']), None)
    if not isinstance(receipt, dict):
        raise RuntimeError(MSG.ORDER_DELIVERY_REWARD_LEGACY_REVIEW)
    plan = receipt.get('plan')
    if not isinstance(plan, dict):
        from app.services import hp_service, squad_service
        total = int(receipt['total_hp'])
        shares = squad_service.squad_share_plan(order_id, total, order['user_id'], campus_id=order.get('campus_id'))
        members = [{'user_id': member.get('user_id') if member.get('is_registered') else None,
                    'email': (member.get('email') or '').strip().lower(), 'hp': shares['share']}
                   for member in shares.get('all_members', [])]
        if int(receipt['owner_hp']) != shares['owner_share']:
            raise RuntimeError(MSG.ORDER_DELIVERY_REWARD_PLAN_CHANGED)
        if food_spend is None:
            items = order.get('order_items')
            if not isinstance(items, list):
                items = db.table('order_items').select('options_snapshot').eq('order_id', order_id).execute() or []
            food_plan = next(((item.get('options_snapshot') or {}).get('_food_hp_plan') for item in items
                              if isinstance(item.get('options_snapshot'), dict) and '_food_hp_plan' in item['options_snapshot']), None)
            food_spend = food_plan['food_spend'] if food_plan else float(order.get('subtotal') or 0)
        welcome = int(get_validated_setting(db, 'welcome_bonus_hp', default=current_app.config.get('WELCOME_BONUS_HP', 100), minimum=0))
        welcome = round(welcome * hp_service._get_hp_multiplier(order.get('campus_id')))
        bonus_pct = int(get_validated_setting(db, 'squad_hp_bonus_pct', default=30, minimum=0, maximum=100, campus_id=order.get('campus_id')))
        plan = {'members': members,
                'unlock_amount': math.floor(float(food_spend) * hp_service.get_food_earn_rate() * hp_service._get_unlock_rate()),
                'welcome_amount': welcome,
                'squad_bonus': (total * bonus_pct) // 100 if shares['registered'] else 0}
    result = db.rpc('hg_complete_delivery_rewards_atomic', {
        'p_order_id': order_id, 'p_plan': plan,
        'p_notes': {'welcome': MSG.HP_DELIVERY_WELCOME_NOTE, 'squad_split': MSG.HP_DELIVERY_SQUAD_NOTE,
                    'squad_bonus': MSG.HP_DELIVERY_SQUAD_BONUS_NOTE}})
    if not isinstance(result, dict) or not result.get('success'):
        raise RuntimeError(MSG.ORDER_DELIVERY_HP_PENDING)
    return result
