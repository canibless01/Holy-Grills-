"""Select one unspent food-HP entitlement; consumption belongs to delivery SQL."""
import math
from app.messages import MSG


def next_food_hp_multiplier(db,user_id,campus_id,*,order_id=None):
    if not user_id:
        return {'multiplier':1.0,'source':None,'receipt_id':None}
    if order_id:
        logs=db.table('order_status_logs').select('metadata').eq('order_id',order_id).order('created_at').limit(50).execute() or []
        plan=next((r['metadata']['hp_bonus_plan'] for r in logs if isinstance(r.get('metadata'),dict) and 'hp_bonus_plan' in r['metadata']),None)
        if plan is not None:
            if plan.get('source')=='none':
                return {'multiplier':1.0,'source':None,'receipt_id':None}
            value=float(plan.get('multiplier'))
            if plan.get('source')!='spin' or not math.isfinite(value) or not 1.01<=value<=10:
                raise ValueError(MSG.CHECKOUT_REWARD_UNAVAILABLE)
            # SQL revalidates the exact reservation under lock. The log remains
            # readable on replay after consumption or zero-food release.
            return {'multiplier':value,'source':'spin','receipt_id':plan.get('receipt_id')}
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


def choose_food_hp_reward(db,user_id,campus_id,choice):
    plan={'source':'none','multiplier':1.0}
    if not user_id:
        if choice!='none':
            raise ValueError(MSG.CHECKOUT_REWARD_UNAVAILABLE)
        return plan,[]
    profile=db.table('profiles').select('is_active,campus_id,next_order_hp_multiplier').eq('id',user_id).single().execute()
    if not profile or not profile.get('is_active') or profile.get('campus_id')!=campus_id:
        raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
    choices=[]
    value=float(profile.get('next_order_hp_multiplier') or 1)
    if not math.isfinite(value):
        raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
    if value>1:
        choices.append({'id':'legacy','source':'legacy','multiplier':value,'name':MSG.CHECKOUT_LEGACY_HP_NAME})
    rows=(db.table('exclusive_spin_fulfillments').select('id,prize_name,result_snapshot')
          .eq('user_id',user_id).or_(f'campus_id.eq.{campus_id},campus_id.is.null').eq('status','pending')
          .is_('applied_order_id','null').eq('result_snapshot->>prize_type','hp_multiplier').order('created_at').order('id').execute()) or []
    for row in rows:
        value=float((row.get('result_snapshot') or {}).get('reward_config',{}).get('multiplier'))
        if not math.isfinite(value) or not 1.01<=value<=10:
            raise ValueError(MSG.ORDER_PRICE_UNVERIFIED)
        choices.append({'id':row['id'],'receipt_id':row['id'],'source':'spin','multiplier':value,'name':row.get('prize_name') or MSG.CHECKOUT_HP_REWARD_NAME})
    if choice=='none':
        return plan,choices
    selected=next((r for r in choices if r['id']==choice),None)
    if selected is None:
        raise ValueError(MSG.CHECKOUT_REWARD_UNAVAILABLE)
    return {k:v for k,v in selected.items() if k!='id'},choices
