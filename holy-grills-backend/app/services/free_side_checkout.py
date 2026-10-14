"""Read-only cart-side contract; the order transaction owns consumption."""
from datetime import datetime, timezone
from app.messages import MSG


def quote_free_sides(db, user_id, campus_id):
    result = {'enabled': False, 'items': []}
    if not user_id:
        return result
    flag = db.table('feature_flags').select('is_active').eq('feature_name', 'free_side_credits').is_('campus_id', 'null').single().execute()
    if not flag or not flag.get('is_active'):
        return result
    result['enabled'] = True
    rows = (db.table('cart_free_side_selections').select('id,campus_id,free_side_item_id,free_side_items(id,name,is_active,campus_id)')
            .eq('user_id', user_id).order('created_at').order('id').execute()) or []
    if not rows:
        return result
    for selection in rows:
        item = selection.get('free_side_items') or {}
        if isinstance(item, list):
            item = item[0] if item else {}
        if selection.get('campus_id') not in (None, campus_id) or item.get('campus_id') not in (None, campus_id) or not item.get('is_active'):
            raise ValueError(MSG.FREE_SIDE_SELECTION_INVALID)
        result['items'].append({'selection_id': selection['id'], 'free_side_item_id': item['id'], 'name': item['name']})
    credits = (db.table('free_side_credits').select('credits_remaining').eq('user_id', user_id)
               .or_(f'campus_id.eq.{campus_id},campus_id.is.null').gt('credits_remaining', 0)
               .gte('expires_at', datetime.now(timezone.utc).isoformat()).execute()) or []
    if sum(int(row['credits_remaining']) for row in credits) < len(rows):
        raise ValueError(MSG.FREE_SIDE_SELECTION_INVALID)
    return result
