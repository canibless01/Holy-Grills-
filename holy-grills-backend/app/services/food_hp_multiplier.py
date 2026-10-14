"""Select one unspent food-HP entitlement; consumption belongs to delivery SQL."""
import math


def next_food_hp_multiplier(db,user_id,campus_id):
    if not user_id:
        return {'multiplier':1.0,'source':None,'receipt_id':None}
    profile=db.table('profiles').select('next_order_hp_multiplier').eq('id',user_id).single().execute()
    if not profile:
        raise ValueError('profile unavailable')
    legacy=float(profile.get('next_order_hp_multiplier') or 1)
    if not math.isfinite(legacy):
        raise ValueError('invalid multiplier')
    if legacy>1:
        return {'multiplier':legacy,'source':'legacy','receipt_id':None}
    rows=(db.table('exclusive_spin_fulfillments').select('id,result_snapshot')
          .eq('user_id',user_id).or_(f'campus_id.eq.{campus_id},campus_id.is.null')
          .eq('status','pending').is_('applied_order_id','null')
          .eq('result_snapshot->>prize_type','hp_multiplier').order('created_at').order('id').limit(1).execute()) or []
    if not rows:
        return {'multiplier':1.0,'source':None,'receipt_id':None}
    value=(rows[0].get('result_snapshot') or {}).get('reward_config',{}).get('multiplier')
    if isinstance(value,bool):
        raise ValueError('invalid multiplier')
    value=float(value)
    if not math.isfinite(value) or not 1.01<=value<=10:
        raise ValueError('invalid multiplier')
    return {'multiplier':value,'source':'spin','receipt_id':rows[0]['id']}
