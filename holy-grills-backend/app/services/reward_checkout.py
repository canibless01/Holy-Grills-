"""Build server-owned reward lines; the order RPC claims them atomically."""
from app.messages import MSG
from app.utils.validators import validate_uuid
from app.services.reward_promises import earned_reward


def reward_checkout_plan(db, user_id, campus_id, redemption_id=None, include_next_order=True):
    """Explicit claims fail closed. Unavailable automatic rewards remain saved."""
    if redemption_id and (not user_id or not validate_uuid(redemption_id)):
        raise ValueError(MSG.REWARD_REDEMPTION_UNAVAILABLE)
    if not user_id:
        return {'items': [], 'claims': []}
    rows = []
    if redemption_id:
        row = (db.table('reward_redemptions').select('*').eq('id', redemption_id)
               .eq('user_id', user_id).single().execute())
        if not row:
            raise ValueError(MSG.REWARD_REDEMPTION_UNAVAILABLE)
        rows.append((row, True))
    if include_next_order:
        automatic = (db.table('reward_redemptions').select('*').eq('user_id', user_id)
                     .eq('status', 'fulfilled').eq('delivery_mode', 'next_order')
                     .is_('attached_order_id', 'null').is_('used_at', 'null').execute()) or []
        rows.extend((row, False) for row in automatic if row['id'] != redemption_id)
    items, claims = [], []
    for row, explicit in sorted(rows, key=lambda pair: pair[0]['id']):
        valid = (row.get('user_id') == user_id and row.get('status') == 'fulfilled'
                 and not row.get('attached_order_id') and not row.get('used_at')
                 and row.get('campus_id') in (None, campus_id))
        reward = earned_reward(row) if valid else None
        if valid and reward is None:
            reward = (db.table('rewards').select('id,name,reward_type,fulfillment_type,metadata,campus_id')
                      .eq('id', row['reward_id']).single().execute())
        valid = valid and bool(reward) and reward.get('campus_id') in (None, campus_id)
        metadata = (reward.get('metadata') or {}) if reward else {}
        menu_id = metadata.get('menu_item_id') if isinstance(metadata, dict) else None
        if valid and menu_id and not validate_uuid(menu_id):
            valid = False
        if valid and menu_id:
            menu = (db.table('menu_items').select('id,campus_id,is_available,deleted_at')
                    .eq('id', menu_id).single().execute()) if menu_id else None
            valid = bool(menu and menu.get('is_available') and not menu.get('deleted_at')
                         and menu.get('campus_id') in (None, campus_id))
            if valid:
                availability = (db.table('menu_item_availability').select('is_available,opens_at,closes_at')
                                .eq('menu_item_id', menu_id).eq('campus_id', campus_id).single().execute())
                if availability:
                    from app.utils.tz import is_within_availability_window
                    valid = bool(availability.get('is_available') and is_within_availability_window(
                        availability.get('opens_at'), availability.get('closes_at')))
        elif valid:
            menu_id = None
        if not valid:
            if explicit:
                raise ValueError(MSG.REWARD_REDEMPTION_UNAVAILABLE)
            continue
        claims.append(str(row['id']))
        items.append({'menu_item_id': menu_id, 'name_snapshot': reward['name'], 'quantity': 1,
                      'price_snapshot': 0, 'line_total': 0, 'hp_earn_snapshot': 0,
                      'hp_multiplier_snapshot': 1, 'selected_variations': [], 'is_addon': False,
                      '_addon_selections': [], 'options_snapshot': {
                          'reward_redemption_id': str(row['id']), 'reward_name': reward['name'],
                          'reward_type': reward.get('reward_type')}})
    return {'items': items, 'claims': claims}
