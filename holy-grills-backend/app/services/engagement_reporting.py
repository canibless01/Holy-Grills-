"""First-party engagement measurement and the existing operations-email sidecar."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.validators import validate_uuid
logger=get_logger(__name__)
WAT=ZoneInfo('Africa/Lagos')
PATHS=frozenset(('/', '/menu','/menu/:item','/checkout','/register','/login','/dashboard','/rewards','/wallet','/profile','/orders','/orders/:order','/events','/events/:event','/marketplace','/marketplace/:item','/referrals','/streak','/squads','/our-story','/faq','/contact'))

def record_page(db,body,user_id=None):
    if not isinstance(body,dict) or body.get('path') not in PATHS or any(not validate_uuid(body.get(k)) for k in ('id','visitor_id','campus_id')):
        return {'error':'invalid'}
    return db.rpc('hg_record_engagement_page',{'p_id':body['id'],'p_visitor':body['visitor_id'],'p_user':user_id,'p_campus':body['campus_id'],'p_path':body['path']})

def report(db,actor_id,scope,start,end):
    return db.rpc('hg_engagement_report',{'p_actor':actor_id,'p_scope':scope,'p_start':start,'p_end':end})

def operations_lines(db,row):
    payload=row.get('payload') or {}
    try:
        start=payload.get('period_start');end=payload.get('period_end')
        if not start or not end:
            start=datetime.fromisoformat(str(payload['from'])).replace(tzinfo=WAT).isoformat()
            end=(datetime.fromisoformat(str(payload['to'])).replace(tzinfo=WAT)+timedelta(days=1)).isoformat()
        data=db.rpc('hg_engagement_summary',{'p_campus':row['campus_id'],'p_start':start,'p_end':end,'p_include_hp':True})
        if not isinstance(data,dict) or data.get('error'):raise ValueError('summary unavailable')
        hp=data.get('hp') or {};streak=data.get('streaks') or {}
        lines=[MSG.OPERATIONS_ENGAGEMENT_TITLE,
          MSG.OPERATIONS_ENGAGEMENT_TOTAL.format(active=data.get('active_users',0),visitors=data.get('visitors',0),views=data.get('page_views',0)),
          MSG.OPERATIONS_ENGAGEMENT_FUNNEL.format(**(data.get('funnel') or {'menu_visitors':0,'checkout_after_menu':0,'paid_linked_accounts':0})),
          MSG.OPERATIONS_STREAK_TOTAL.format(qualified=streak.get('qualified_weeks',0),failed=streak.get('failed_weeks',0)),
          MSG.OPERATIONS_HP_TOTAL.format(active=hp.get('active',0),pending=hp.get('pending',0),difference=hp.get('difference',0))]
        sources=sorted([s for s in hp.get('sources',[]) if s.get('active') or s.get('pending')],key=lambda s:-(s.get('active',0)+s.get('pending',0)))
        lines += [MSG.OPERATIONS_HP_SOURCE.format(source=s['source'].replace('_',' '),active=s.get('active',0),pending=s.get('pending',0)) for s in sources[:5]]
        if len(sources)>5:lines.append(MSG.OPERATIONS_HP_MORE_SOURCES)
        lines.append(MSG.OPERATIONS_ENGAGEMENT_BASIS)
        return lines
    except Exception:
        logger.warning('Engagement summary unavailable for an operations report',exc_info=True)
        return [MSG.OPERATIONS_ENGAGEMENT_UNAVAILABLE]
