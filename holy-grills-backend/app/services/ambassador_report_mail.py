"""Weekly/monthly ambassador digests; count-only snapshots and durable outbox."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from flask import current_app
from app.messages import MSG
from app.utils.logger import get_logger
WAT=ZoneInfo('Africa/Lagos')
logger=get_logger(__name__)


def due_periods(now=None):
    now=(now or datetime.now(WAT)).astimezone(WAT)
    monday=(now-timedelta(days=now.weekday())).replace(hour=9,minute=0,second=0,microsecond=0)
    first=now.replace(day=1,hour=9,minute=0,second=0,microsecond=0)
    result=[]
    if monday<=now<monday+timedelta(days=2):
        result.append(('weekly',(monday-timedelta(days=7)).date().isoformat()))
    if first<=now<first+timedelta(days=2):
        result.append(('monthly',(first-timedelta(days=1)).replace(day=1).date().isoformat()))
    return result


def render(data,person):
    # Whitelisted counts only: do not serialize raw insights/profile/financial rows.
    def counts(value,keys):return {k:int(value.get(k) or 0) for k in keys}
    name=person.get('nickname') or (person.get('name') or '').split(' ')[0] or MSG.ENGAGEMENT_CAMPAIGN_FRIEND
    lines=[MSG.AMBASSADOR_MAIL_HELLO.format(name=name),
           MSG.AMBASSADOR_MAIL_PERIOD.format(campus=data['campus_name'],start=data['period_start'],end=data['period_end']),
           MSG.AMBASSADOR_MAIL_YOURS.format(**counts(person['progress'],('signups','orders','shared_count','assigned_count'))),
           MSG.AMBASSADOR_MAIL_MONTH.format(month=data['month'],**counts(person['month_progress'],('signups','orders','shared_count','monthly_share_target'))),
           MSG.AMBASSADOR_MAIL_TIER.format(tier=person.get('current_tier') or MSG.AMBASSADOR_MAIL_STARTING),
           MSG.AMBASSADOR_MAIL_TEAM.format(**counts(data['team'],('ambassadors','signups','orders','shared_count'))),
           MSG.AMBASSADOR_MAIL_TEAM_TIERS]
    lines += [MSG.AMBASSADOR_MAIL_TIER_COUNT.format(tier=t.get('tier') or MSG.AMBASSADOR_MAIL_STARTING,members=int(t['members'])) for t in data['tiers']]
    url=(current_app.config.get('FRONTEND_URL') or 'https://holygrills.online').split(',')[0].strip().rstrip('/')+'/dashboard'
    lines += [MSG.AMBASSADOR_MAIL_BASIS,MSG.AMBASSADOR_MAIL_CLOSING,MSG.AMBASSADOR_MAIL_LINK.format(url=url),MSG.AMBASSADOR_MAIL_PREFERENCES]
    title=MSG.AMBASSADOR_MAIL_WEEKLY_SUBJECT if data['kind']=='weekly' else MSG.AMBASSADOR_MAIL_MONTHLY_SUBJECT
    return title,'\n\n'.join(lines)


def capture_due(db,now=None):
    stats={'queued':0,'duplicates':0,'skipped':0,'errors':0}
    for kind,start in due_periods(now):
        try:
            campuses=db.rpc('hg_due_ambassador_report_campuses',{'p_kind':kind,'p_start':start})
            if not isinstance(campuses,list):raise ValueError('campus_read_unavailable')
            for campus in campuses:
                data=db.rpc('hg_ambassador_mail_data',{'p_campus':campus['campus_id'],'p_kind':kind,'p_start':start})
                if not isinstance(data,dict) or data.get('error'):raise ValueError('report_unavailable')
                for person in data['people']:
                    title,body=render(data,person)
                    result=db.rpc('hg_queue_ambassador_report',{'p_user':person['user_id'],'p_campus':campus['campus_id'],'p_kind':kind,'p_start':start,'p_title':title,'p_body':body})
                    if not isinstance(result,dict) or result.get('error'):raise ValueError('queue_unavailable')
                    if result.get('queued'):stats['queued']+=1
                    elif result.get('duplicate'):stats['duplicates']+=1
                    else:stats['skipped']+=1
        except Exception as exc:
            stats['errors']+=1
            logger.warning('Ambassador report capture deferred: %s',type(exc).__name__)
    return stats
