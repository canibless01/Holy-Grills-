"""Verified roster and shareable weekly summaries, read in one database call."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from flask import current_app
from app.messages import MSG
from app.services.ambassador_service import AmbassadorError, parse_month

WAT=ZoneInfo('Africa/Lagos')
def week_start(value=None):
    try:
        day=date.fromisoformat(value) if value else datetime.now(WAT).date()
    except (ValueError,TypeError):
        raise AmbassadorError(MSG.AMBASSADOR_REPORT_RANGE)
    return day-timedelta(days=day.weekday())

def insights(db,actor_id,scope,month=None,week=None,only=None):
    result=db.rpc('hg_ambassador_insights',{'p_actor':actor_id,'p_scope':scope,'p_month':parse_month(month),'p_week':week_start(week).isoformat(),'p_only':only})
    if isinstance(result,dict) and result.get('error'):
        raise AmbassadorError(MSG.RESOURCE_ACCESS_DENIED if result['error']=='forbidden' else MSG.AMBASSADOR_REPORT_RANGE,status=403 if result['error']=='forbidden' else 400)
    if not isinstance(result,dict) or not isinstance(result.get('ambassadors'),list):
        raise AmbassadorError(MSG.SERVICE_UNAVAILABLE,status=503)
    origin=current_app.config.get('FRONTEND_URL','').rstrip('/')
    for row in result['ambassadors']:
        code=(row.get('profile') or {}).get('referral_code')
        from urllib.parse import urlencode
        row['tracking_link']=origin+'/register?'+urlencode({'ref':code}) if code else None
    return result

def weekly(db,actor_id,scope,week=None):
    start=week_start(week)
    data=insights(db,actor_id,scope,start.strftime('%Y-%m'),start.isoformat())
    rows=[]
    for item in data['ambassadors']:
        profile=item['profile'];metrics=item['week']
        rows.append({'ambassador_id':item['ambassador']['profile_id'],'name':profile.get('nickname') or profile.get('full_name') or MSG.AMBASSADOR_REPORT_PERSON,**metrics})
    totals={k:sum(row.get(k,0) for row in rows) for k in ('signups','orders','retained_order_value','assigned_count','shared_count')}
    lines=[MSG.AMBASSADOR_WEEKLY_TITLE.format(start=data['week_start'],end=data['week_end']),
           MSG.AMBASSADOR_WEEKLY_TOTAL.format(**totals)]
    lines += [MSG.AMBASSADOR_WEEKLY_ROW.format(**row) for row in rows]
    return {'week_start':data['week_start'],'week_end':data['week_end'],'as_of':data.get('as_of'),
            'order_basis':data['order_basis'],'share_basis':data['share_basis'],'ambassadors':rows,'totals':totals,'share_text':'\n\n'.join(lines)}
