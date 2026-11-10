"""Real dispatcher/route code, with transport and database boundaries controlled."""
from copy import deepcopy
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask, g
from app.services import notification_outbox as outbox, notification_service as service
from app.routes import notifications as routes
from app.db import SupabaseError

ID='11111111-1111-4111-8111-111111111111'
TOKEN='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)

@pytest.fixture
def setup_dispatch():
    db=MagicMock(); q=db.table.return_value
    for name in ('select','eq','single'):getattr(q,name).return_value=q
    q.execute.return_value={'email':'student@example.com','campus_id':ID}
    claim={'state':'claimed','channel':'email','token':TOKEN,'key':ID,'payload':{'notification':{
        'user_id':ID,'email':'student@example.com','name':'Student','type':'order_confirmed','title':'Receipt','body':'Saved','metadata':{}}}}
    calls=[]
    def rpc(name,params):
        calls.append((name,deepcopy(params)))
        if name=='hg_claim_notification_dispatch_v2':return deepcopy(claim)
        return True
    db.rpc.side_effect=rpc
    with patch.object(outbox,'get_db',return_value=db),patch.object(outbox,'effective_preferences',return_value={}),patch.object(service,'_prepare_notification_email',return_value={'provider':'resend','subject':'Frozen'}),patch.object(service,'_deliver_email_attempt',return_value={'state':'accepted','provider':'resend','provider_message_id':'receipt'}) as email,patch.object(service,'_get_onesignal_creds',return_value=('app','key')),patch.object(service,'_deliver_push_attempt',return_value={'state':'accepted','provider':'onesignal'}) as push:
        yield db,claim,calls,email,push

@pytest.mark.parametrize('state',['busy','sent','uncertain','failed','missing','deferred'])
def test_nonclaimed_dispatch_never_calls_provider(setup_dispatch,state):
    _,claim,_,email,push=setup_dispatch;claim['state']=state
    assert outbox.dispatch_notification(ID)['state']==state
    email.assert_not_called();push.assert_not_called()

def test_handoff_is_persisted_before_provider_and_real_receipt_saved(setup_dispatch):
    _,_,calls,email,_=setup_dispatch
    def send(prepared):
        assert calls[-1][0]=='hg_begin_notification_dispatch'
        return {'state':'accepted_fallback','delivered_by':'onesignal','fallback':{'provider_message_id':'actual'}}
    email.side_effect=send
    assert outbox.dispatch_notification(ID)['state']=='accepted_fallback'
    assert calls[-1][1]['p_outcome']['fallback']['provider_message_id']=='actual'

@pytest.mark.parametrize('receipt,expected',[
 ({'state':'unknown'},'uncertain'),({'state':'rejected'},'uncertain'),({'state':'quota'},'retry'),
 ({'state':'not_configured'},'retry'),({'state':'skipped'},'skipped'),
 ({'state':'quota','fallback':{'state':'unknown'}},'uncertain'),
 ({'state':'quota','fallback':{'state':'not_configured'}},'retry')])
def test_only_known_nonsends_are_retried(setup_dispatch,receipt,expected):
    _,_,_,email,push=setup_dispatch;email.return_value=receipt
    assert outbox.dispatch_notification(ID)['state']==expected
    email.assert_called_once();push.assert_not_called()

def test_interrupted_email_is_uncertain_and_never_uses_push_fallback(setup_dispatch):
    _,_,calls,email,push=setup_dispatch;email.side_effect=RuntimeError('interrupted')
    assert outbox.dispatch_notification(ID)['state']=='uncertain'
    assert calls[-1][1]['p_outcome']['state']=='uncertain';push.assert_not_called()

def test_changed_recipient_is_not_sent_private_snapshot(setup_dispatch):
    db,_,_,email,_=setup_dispatch;db.table.return_value.execute.return_value={'email':'changed@example.com'}
    assert outbox.dispatch_notification(ID)['error']=='recipient_email_changed';email.assert_not_called()

def test_optout_during_queue_wait_prevents_send(setup_dispatch):
    _,_,_,email,push=setup_dispatch
    with patch.object(outbox,'effective_preferences',return_value={'email_enabled':False}):
        assert outbox.dispatch_notification(ID)['error']=='recipient_opted_out'
    email.assert_not_called();push.assert_not_called()

def test_cancelled_campaign_prevents_send(setup_dispatch):
    db,claim,_,email,_=setup_dispatch;claim['payload']['notification']['blast_id']=TOKEN
    db.table.return_value.execute.side_effect=[{'email':'student@example.com'},{'status':'cancelled'}]
    assert outbox.dispatch_notification(ID)['state']=='cancelled';email.assert_not_called()

def test_lost_lease_never_reaches_transport(setup_dispatch):
    db,_,_,email,push=setup_dispatch;original=db.rpc.side_effect
    db.rpc.side_effect=lambda name,params: False if name=='hg_begin_notification_dispatch' else original(name,params)
    assert outbox.dispatch_notification(ID)['state']=='lease_lost';email.assert_not_called();push.assert_not_called()

def test_recovered_push_uses_frozen_payload_and_key(setup_dispatch):
    _,claim,_,email,push=setup_dispatch;claim['channel']='push'
    prepared={'app_id':'app','idempotency_key':ID,'contents':{'en':'Frozen'}}
    claim['payload']['prepared']=prepared
    outbox.dispatch_notification(ID);outbox.dispatch_notification(ID)
    assert push.call_count==2
    for call in push.call_args_list:
        assert call.kwargs['prepared']==prepared and call.kwargs['idempotency_key']==ID
    email.assert_not_called()

def test_missing_push_config_does_not_freeze_invalid_app_id(setup_dispatch):
    _,claim,calls,_,push=setup_dispatch;claim['channel']='push'
    with patch.object(service,'_get_onesignal_creds',return_value=(None,None)):
        assert outbox.dispatch_notification(ID)['state']=='retry'
    assert not any(name=='hg_begin_notification_dispatch' for name,_ in calls);push.assert_not_called()

def test_recovery_scan_stops_at_time_budget():
    db=MagicMock();db.rpc.return_value=[ID,TOKEN]
    with patch.object(outbox,'get_db',return_value=db),patch.object(outbox,'monotonic',side_effect=[0,1,46]),patch.object(outbox,'dispatch_notification',return_value={'state':'sent'}) as dispatch:
        result=outbox.recover_due_notifications()
    assert result=={'checked':1,'due':2,'sent':1};dispatch.assert_called_once_with(ID)
    db.rpc.assert_called_once_with('hg_due_notification_dispatch',{'p_limit':50})

def test_thread_entry_points_only_claim_durable_records():
    with patch.object(outbox,'dispatch_notification') as dispatch:
        service._dispatch_email_async(ID,'Title','Body',TOKEN)
        service._dispatch_push_async(ID,'Title','Body',None,TOKEN)
    assert dispatch.call_count==2
    for call in dispatch.call_args_list:assert call.args==(TOKEN,)

@pytest.mark.parametrize('data',[None,[],{}, {'review_id':TOKEN,'outcome':'sent','provider':'resend','evidence':'Provider confirmed send'}, {'review_id':TOKEN,'outcome':None,'provider':'resend','evidence':'Provider confirmed send'}])
def test_review_rejects_invalid_input_without_db_write(data):
    with app.test_request_context(json=data),patch.object(routes,'get_db') as db:
        _,status=routes.notification_recovery_review.__wrapped__(ID)
        assert status==400;db.assert_not_called()

def test_review_passes_actor_evidence_and_stable_review_key():
    data={'review_id':TOKEN,'outcome':'not_sent','provider':'resend','evidence':'Provider explicitly rejected sender'}
    with app.test_request_context(json=data),patch.object(routes,'get_db') as db:
        g.user_id=ID;db.return_value.rpc.return_value={'status':'queued','idempotent':True}
        assert routes.notification_recovery_review.__wrapped__(ID).json['idempotent'] is True
        assert db.return_value.rpc.call_args.args[1]=={'p_actor_id':ID,'p_id':ID,'p_review_id':TOKEN,'p_outcome':'not_sent','p_provider':'resend','p_message_id':None,'p_evidence':data['evidence']}

@pytest.mark.parametrize('code,status',[('42501',403),('P0001',409)])
def test_review_handles_scope_and_changed_state_without_leaking_db_details(code,status):
    data={'review_id':TOKEN,'outcome':'not_sent','provider':'resend','evidence':'Provider explicitly rejected sender'}
    with app.test_request_context(json=data),patch.object(routes,'get_db') as db:
        g.user_id=ID;db.return_value.rpc.side_effect=SupabaseError('private snapshot',400,{'code':code})
        response,actual=routes.notification_recovery_review.__wrapped__(ID)
        assert actual==status and 'private snapshot' not in response.get_data(as_text=True)

@pytest.mark.parametrize('role,active,status',[('student',True,403),('rider',True,403),('admin',False,403),('admin',True,200),('super_admin',True,200)])
def test_actual_decorator_restricts_recovery_access(role,active,status):
    from app.middleware import auth
    server=Flask(__name__);server.register_blueprint(routes.notifications_bp,url_prefix='/notifications')
    db=MagicMock();db.auth_get_user.return_value={'id':ID}
    query=db.table.return_value
    for name in ('select','eq','single'):getattr(query,name).return_value=query
    query.execute.return_value={'id':ID,'role':role,'is_active':active,'campus_id':TOKEN}
    db.rpc.return_value=[]
    with patch.object(auth,'get_db',return_value=db),patch.object(routes,'get_db',return_value=db):
        response=server.test_client().get('/notifications/dispatch/recovery',headers={'Authorization':'Bearer synthetic-local-only'})
    assert response.status_code==status
    if status==403:db.rpc.assert_not_called()
    else:assert response.json=={'deliveries':[]}

def test_delivery_result_is_not_reported_persisted_after_lease_loss(setup_dispatch):
    db,_,_,email,_=setup_dispatch;original=db.rpc.side_effect
    db.rpc.side_effect=lambda name,params: False if name=='hg_finish_notification_dispatch' else original(name,params)
    assert outbox.dispatch_notification(ID)['state']=='lease_lost';email.assert_called_once()


def ticket_claim(setup_dispatch, **changes):
    db,claim,calls,email,push=setup_dispatch
    claim['payload'].update(kind='event_ticket_email',ticket_id=TOKEN,event_id=ID)
    snapshot=claim['payload']['notification'];snapshot['user_id']=None
    snapshot['metadata']={'event_title':'Grill <Night>','event_date':'2026-11-09','event_location':'FUTA'}
    db.table.return_value.execute.return_value={'event_id':ID,'user_id':None,'guest_email':'Student@Example.com','status':'confirmed','payment_status':'paid',**changes}
    return db,claim,calls,email,push


def test_guest_ticket_builds_frozen_local_qr_and_transactional_email(setup_dispatch):
    db,_,_,email,_=ticket_claim(setup_dispatch)
    with patch.object(service,'get_email_provider',return_value='resend'),patch.object(outbox,'effective_preferences') as prefs:
        assert outbox.dispatch_notification(TOKEN)['state']=='accepted'
    prepared=email.call_args.args[0]
    assert prepared['to_email']=='student@example.com' and prepared['transactional'] is True
    assert 'data:image/png;base64,' in prepared['html_body']
    assert 'Grill &lt;Night&gt;' in prepared['html_body'] and '<Night>' not in prepared['html_body']
    assert 'api.qrserver' not in prepared['html_body'];prefs.assert_not_called()
    assert all(call.args[0]!='profiles' for call in db.table.call_args_list)


@pytest.mark.parametrize('changes',[{'status':'cancelled'},{'payment_status':'pending'},{'payment_status':'refunded'},{'event_id':TOKEN},{'user_id':ID}])
def test_ticket_state_or_owner_change_cancels_dispatch(setup_dispatch,changes):
    _,_,_,email,push=ticket_claim(setup_dispatch,**changes)
    assert outbox.dispatch_notification(TOKEN)['state']=='cancelled'
    email.assert_not_called();push.assert_not_called()


def test_changed_guest_email_does_not_receive_old_ticket(setup_dispatch):
    _,_,_,email,_=ticket_claim(setup_dispatch,guest_email='new@example.com')
    assert outbox.dispatch_notification(TOKEN)['error']=='recipient_email_changed';email.assert_not_called()


def test_guest_recovery_never_rebuilds_saved_provider_payload(setup_dispatch):
    _,claim,_,email,_=ticket_claim(setup_dispatch)
    prepared={'to_email':'student@example.com','provider':'onesignal','subject':'Frozen title','html_body':'Frozen QR','transactional':True}
    claim['payload']['prepared']=prepared
    with patch('app.utils.email._prepare_qr_ticket_email') as build:
        assert outbox.dispatch_notification(TOKEN)['state']=='accepted'
    build.assert_not_called();email.assert_called_once_with(prepared)


def test_guest_timeout_keeps_uncertain_state_without_second_provider(setup_dispatch):
    _,claim,_,email,push=ticket_claim(setup_dispatch)
    claim['payload']['prepared']={'to_email':'student@example.com','provider':'onesignal','subject':'Frozen title','html_body':'Frozen QR','transactional':True}
    email.return_value={'state':'unknown','provider':'onesignal'}
    assert outbox.dispatch_notification(TOKEN)['state']=='uncertain'
    email.assert_called_once();push.assert_not_called()


@pytest.mark.parametrize('status',['sent','uncertain','failed',None])
def test_ticket_wake_does_not_resend_terminal_or_missing_rows(status):
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'status':status} if status else None
    with patch.object(outbox,'get_db',return_value=db),patch('threading.Thread') as thread:
        assert outbox.start_ticket_email_dispatch(TOKEN) is False
    thread.assert_not_called()


def test_ticket_wake_uses_saved_dispatch_id_and_existing_thread_transport():
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'status':'queued'}
    with patch.object(outbox,'get_db',return_value=db),patch('threading.Thread') as thread:
        assert outbox.start_ticket_email_dispatch(TOKEN) is True
    assert thread.call_args.kwargs=={'target':outbox.dispatch_notification,'args':(TOKEN,),'daemon':True}
    thread.return_value.start.assert_called_once()


@pytest.mark.parametrize('grant',[{}, {'ambassador_id':ID,'status':'voided'}, {'ambassador_id':TOKEN,'status':'issued'}])
def test_voided_missing_or_reassigned_ambassador_grant_is_not_dispatched(setup_dispatch,grant):
    db,claim,calls,email,push=setup_dispatch
    claim['channel']='push'
    claim['payload']['notification'].update(type='ambassador_grant_issued',metadata={'reference_type':'ambassador_grant','reference_id':TOKEN})
    db.table.return_value.execute.side_effect=[{'email':'student@example.com'},grant]
    assert outbox.dispatch_notification(ID)['state']=='cancelled'
    email.assert_not_called();push.assert_not_called()
    assert all(name!='hg_begin_notification_dispatch' for name,_ in calls)


def test_issued_ambassador_grant_dispatches_saved_receipt_once(setup_dispatch):
    db,claim,calls,email,push=setup_dispatch
    claim['channel']='push'
    claim['payload']['notification'].update(type='ambassador_grant_issued',action_url='/rewards',metadata={'reference_type':'ambassador_grant','reference_id':TOKEN})
    db.table.return_value.execute.side_effect=[{'email':'student@example.com'},{'ambassador_id':ID,'status':'issued'}]
    assert outbox.dispatch_notification(ID)['state']=='accepted'
    push.assert_called_once();email.assert_not_called()
    assert push.call_args.args[3]=='/rewards'

def test_malformed_ambassador_receipt_is_cancelled_without_private_lookup(setup_dispatch):
    db,claim,calls,email,push=setup_dispatch
    claim['channel']='push';claim['payload']['notification']['type']='ambassador_grant_issued'
    assert outbox.dispatch_notification(ID)['state']=='cancelled'
    assert not any(call.args==('ambassador_grants',) for call in db.table.call_args_list)
    email.assert_not_called();push.assert_not_called()


def test_guest_event_cancellation_notice_is_generic_not_a_new_ticket(setup_dispatch):
    db,claim,_,email,_=ticket_claim(setup_dispatch,status='cancelled',payment_status='refund_pending')
    claim['payload']['kind']='event_status_email'
    claim['payload']['notification'].update(type='event_cancelled',title='Event cancelled',body='Your ticket payment is being refunded.')
    claim['payload']['notification']['metadata']={'event_id':ID,'event_change_id':TOKEN}
    db.table.return_value.execute.side_effect=[{'event_id':ID,'user_id':None,'guest_email':'student@example.com','status':'cancelled','payment_status':'refund_pending'},{'metadata':{'latest_change_id':TOKEN,'lifecycle_status':'cancelled'}}]
    with patch('app.utils.email._prepare_qr_ticket_email') as qr:
        assert outbox.dispatch_notification(TOKEN)['state']=='accepted'
    qr.assert_not_called();email.assert_called_once()


def test_older_event_date_notice_is_not_sent_after_newer_change(setup_dispatch):
    db,claim,_,email,push=setup_dispatch
    claim['payload']['notification']['metadata']={'event_id':ID,'event_change_id':TOKEN}
    db.table.return_value.execute.side_effect=[{'email':'student@example.com'},{'metadata':{'latest_change_id':ID}}]
    assert outbox.dispatch_notification(ID)['error']=='event_notice_superseded'
    email.assert_not_called();push.assert_not_called()


def test_queued_ticket_email_uses_current_rescheduled_date(setup_dispatch):
    db,claim,_,email,_=ticket_claim(setup_dispatch)
    db.table.return_value.execute.side_effect=[{'event_id':ID,'user_id':None,'guest_email':'student@example.com','status':'confirmed','payment_status':'paid'},{'title':'Updated event','starts_at':'2027-12-01T10:00:00Z','location':'New hall','metadata':{'lifecycle_status':'rescheduled'}}]
    with patch('app.utils.email._prepare_qr_ticket_email',return_value={'to_email':'student@example.com'}) as qr:
        assert outbox.dispatch_notification(TOKEN)['state']=='accepted'
    assert qr.call_args.args[2]=='Updated event' and qr.call_args.args[5]=='2027-12-01T10:00:00Z' and qr.call_args.args[6]=='New hall'
