"""Recover saved external notifications; never guess an uncertain email outcome."""
from time import monotonic
from app.db import get_db
from app.services.notification_preferences import effective_preferences, permitted_channels
from app.utils.logger import get_logger

logger=get_logger(__name__)


def dispatch_notification(notification_id):
    db=get_db()
    claim=None
    started=False
    try:
        claim=db.rpc('hg_claim_notification_dispatch',{'p_id':notification_id})
        if not isinstance(claim,dict) or claim.get('state')!='claimed':
            return claim or {'state':'unavailable'}
        channel=claim['channel'];snapshot=claim['payload']['notification']
        def finish(outcome):
            saved=db.rpc('hg_finish_notification_dispatch',{'p_id':notification_id,'p_token':claim['token'],'p_outcome':outcome})
            return outcome if saved is True else {'state':'lease_lost'}
        profile=db.table('profiles').select('email,campus_id,push_enabled,email_notifications').eq('id',snapshot['user_id']).single().execute()
        if not profile:
            return finish({'state':'skipped','error':'recipient_missing'})
        prefs=effective_preferences(db,snapshot['user_id'],profile)
        if channel not in permitted_channels(snapshot['type'],[channel],prefs):
            return finish({'state':'skipped','error':'recipient_opted_out'})
        blast_id=snapshot.get('blast_id')
        if blast_id:
            blast=db.table('notification_blasts').select('status').eq('id',blast_id).single().execute() or {}
            if not blast or blast.get('status') in ('cancelled','canceled'):
                return finish({'state':'cancelled','error':'campaign_cancelled'})
        from app.services import notification_service as service
        meta=snapshot.get('metadata') or {}
        prepared=claim['payload'].get('prepared')
        if channel=='email':
            if str(profile.get('email') or '').strip().lower()!=str(snapshot.get('email') or '').strip().lower():
                return finish({'state':'skipped','error':'recipient_email_changed'})
            if prepared is None:
                rich={key:meta[key] for key in ('body_html','images','cta_blocks') if meta.get(key)}
                prepared=service._prepare_notification_email(snapshot['user_id'],snapshot['title'],snapshot['body'],
                    provider=meta.get('email_provider'),rich_content=rich,blast_id=blast_id,recipient=snapshot)
            if not prepared:
                return finish({'state':'skipped','error':'recipient_email_missing'})
        elif channel=='push':
            if prepared is None:
                if not all(service._get_onesignal_creds()):
                    return finish({'state':'retry','provider':'onesignal','error':'push_not_configured'})
                prepared=service._prepare_notification_push(snapshot['user_id'],snapshot['title'],snapshot['body'],
                    snapshot.get('action_url'),meta.get('urgency'),meta.get('push_image'),claim['key'])
        else:
            return finish({'state':'failed','error':'unsupported_channel'})
        began=db.rpc('hg_begin_notification_dispatch',{'p_id':notification_id,'p_token':claim['token'],'p_prepared':prepared})
        if began is not True:
            return {'state':'lease_lost'}
        started=True
        if channel=='push':
            outcome=service._deliver_push_attempt(snapshot['user_id'],snapshot['title'],snapshot['body'],snapshot.get('action_url'),
                notification_id,prepared=prepared,idempotency_key=claim['key'])
        else:
            outcome=service._deliver_email_attempt(prepared)
            if outcome.get('state') not in ('accepted','accepted_fallback','skipped'):
                final=outcome.get('fallback') or outcome
                state=final.get('state')
                outcome={**outcome,'state':'retry' if state in ('not_configured','quota') else 'uncertain'}
                if state=='skipped':outcome['state']='skipped'
        return finish(outcome)
    except Exception as exc:
        logger.warning('Notification %s dispatch incomplete: %s',notification_id,type(exc).__name__)
        outcome={'state':'uncertain' if started and claim and claim.get('channel')=='email' else 'retry',
                 'error':type(exc).__name__}
        if claim and claim.get('token'):
            try:
                db.rpc('hg_finish_notification_dispatch',{'p_id':notification_id,'p_token':claim['token'],'p_outcome':outcome})
            except Exception:
                pass  # lease expiry remains the durable recovery boundary
        return outcome


def recover_due_notifications(limit=50):
    try:
        ids=get_db().rpc('hg_due_notification_dispatch',{'p_limit':limit})
        if not isinstance(ids,list):raise RuntimeError('Invalid outbox result')
        counts={'checked':0, 'due':len(ids)}
        deadline=monotonic()+45
        for notification_id in ids:
            if monotonic()>=deadline:
                break
            counts['checked']+=1
            result=dispatch_notification(notification_id)
            state=str((result or {}).get('state') or 'unknown')
            counts[state]=counts.get(state,0)+1
        return counts
    except Exception as exc:
        logger.warning('Notification recovery unavailable: %s',type(exc).__name__)
        return {'error':'notification_recovery_unavailable'}
