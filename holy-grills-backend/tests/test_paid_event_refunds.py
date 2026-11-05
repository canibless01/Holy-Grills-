"""Ticket refund financial/transport boundaries; no real provider calls."""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask,g
from app.services import event_refunds as refunds, payment_service as payment
from app.routes import events
from app.db import SupabaseError

ID='11111111-1111-4111-8111-111111111111'
TOKEN='22222222-2222-4222-8222-222222222222'
app=Flask(__name__);app.config['PAYSTACK_SECRET_KEY']='test-only'

@pytest.fixture
def dispatcher():
    db=MagicMock();calls=[]
    claim={'state':'claimed','id':ID,'token':TOKEN,'amount':'1000.00','reference':'original-charge','provider_refund_id':None}
    charge={'id':42,'reference':'original-charge','status':'success','currency':'NGN','amount':105000}
    def rpc(name,params):
        calls.append((name,deepcopy(params)))
        return deepcopy(claim) if name=='hg_claim_event_refund' else True
    db.rpc.side_effect=rpc
    response=MagicMock(status_code=200)
    response.json.return_value={'status':True,'data':{'id':123,'transaction':{'id':42,'reference':'original-charge'},'amount':100000,'currency':'NGN','status':'pending'}}
    with app.app_context(),patch.object(refunds,'get_db',return_value=db),patch.object(payment,'verify_payment',return_value=charge) as verify,patch.object(payment.http_requests,'post',return_value=response) as post,patch.object(payment,'_paystack_get',return_value=response) as get:
        yield db,claim,charge,response,calls,post,get,verify


def test_guest_post_has_frozen_unique_reference_and_waits_for_processing(dispatcher):
    _,_,_,_,calls,post,get,_=dispatcher
    assert refunds.process_event_refund(ID)['state']=='processing'
    assert calls[-2][0]=='hg_begin_event_refund' and calls[-1][1]['p_state']=='processing'
    post.assert_called_once();get.assert_not_called()
    payload=post.call_args.kwargs['json']
    assert payload['amount']==100000 and payload['transaction']=='original-charge'
    assert payload['reference']=='hgticket_'+ID.replace('-','')
    assert post.call_args.kwargs['timeout']==15


def test_gateway_timeout_has_no_transport_retry_or_second_post(dispatcher):
    _,_,_,_,calls,post,get,_=dispatcher;post.side_effect=TimeoutError('uncertain')
    assert refunds.process_event_refund(ID)['state']=='uncertain'
    post.assert_called_once();get.assert_not_called();assert calls[-1][1]['p_state']=='uncertain'


@pytest.mark.parametrize('state',['busy','deferred','uncertain','failed','missing'])
def test_nonclaimable_refunds_never_touch_provider(dispatcher,state):
    _,claim,_,_,_,post,get,verify=dispatcher;claim['state']=state
    assert refunds.process_event_refund(ID)['state']==state
    post.assert_not_called();get.assert_not_called();verify.assert_not_called()


def test_missing_gateway_config_is_safe_before_handoff(dispatcher):
    _,_,_,_,calls,post,get,verify=dispatcher
    with patch.dict(app.config,{'PAYSTACK_SECRET_KEY':''}):
        assert refunds.process_event_refund(ID)['state']=='queued'
    assert not any(name=='hg_begin_event_refund' for name,_ in calls)
    post.assert_not_called();get.assert_not_called();verify.assert_not_called()


@pytest.mark.parametrize('changes',[{'reference':'wrong'},{'amount':99999},{'currency':'USD'},{'status':'failed'},{'id':None}])
def test_original_charge_must_verify_before_any_refund_post(dispatcher,changes):
    _,_,charge,_,calls,post,_,_=dispatcher;charge.update(changes)
    assert refunds.process_event_refund(ID)['state']=='queued'
    assert not any(name=='hg_begin_event_refund' for name,_ in calls);post.assert_not_called()


def test_existing_provider_refund_is_polled_without_post(dispatcher):
    _,claim,_,response,calls,post,get,_=dispatcher
    claim.update(state='checking',provider_refund_id='123')
    response.json.return_value['data'].update(status='processed',transaction=42)
    assert refunds.process_event_refund(ID)['state']=='completed'
    post.assert_not_called();get.assert_called_once()
    assert get.call_args.args[0].endswith('/refund/123')
    assert calls[-1][1]['p_provider_id']=='123'


@pytest.mark.parametrize('changes',[{'transaction':99},{'id':999},{'amount':99999},{'currency':'USD'}])
def test_lookup_mismatch_never_marks_refund_complete(dispatcher,changes):
    _,claim,_,response,calls,post,_,_=dispatcher;claim.update(state='checking',provider_refund_id='123')
    response.json.return_value['data'].update(status='processed',**changes)
    assert refunds.process_event_refund(ID)['state']=='uncertain'
    post.assert_not_called();assert calls[-1][1]['p_provider_id']=='123'


@pytest.mark.parametrize('status,expected',[('pending','processing'),('processing','processing'),('processed','completed'),('failed','failed'),('needs-attention','failed')])
def test_provider_completion_and_manual_attention_are_distinct(dispatcher,status,expected):
    _,claim,_,response,_,post,_,_=dispatcher;claim.update(state='checking',provider_refund_id='123')
    response.json.return_value['data']['status']=status
    assert refunds.process_event_refund(ID)['state']==expected;post.assert_not_called()


def test_lost_begin_lease_prevents_money_post(dispatcher):
    db,_,_,_,_,post,_,_=dispatcher;original=db.rpc.side_effect
    db.rpc.side_effect=lambda name,params: False if name=='hg_begin_event_refund' else original(name,params)
    assert refunds.process_event_refund(ID)['state']=='lease_lost';post.assert_not_called()


def test_uncertain_finish_result_does_not_report_completion(dispatcher):
    db,_,_,_,_,post,_,_=dispatcher;original=db.rpc.side_effect
    db.rpc.side_effect=lambda name,params: False if name=='hg_finish_event_refund' else original(name,params)
    assert refunds.process_event_refund(ID)['state']=='lease_lost';post.assert_called_once()


def test_member_notice_is_saved_before_ack_and_never_calls_gateway(dispatcher):
    _,claim,_,_,calls,post,get,_=dispatcher
    claim.update(state='completed',user_id=TOKEN,notified=False,ticket_id=TOKEN,hp_amount=50)
    with patch('app.services.notification_service.send_notification') as notice:
        assert refunds.process_event_refund(ID)['state']=='completed'
    assert notice.call_args.kwargs['reference_id']==ID and notice.call_args.kwargs['strict'] is True
    assert calls[-1][0]=='hg_ack_event_refund_notice';post.assert_not_called();get.assert_not_called()


def test_failed_member_notice_is_not_acknowledged(dispatcher):
    _,claim,_,_,calls,_,_,_=dispatcher
    claim.update(state='completed',user_id=TOKEN,notified=False,ticket_id=TOKEN,hp_amount=50)
    with patch('app.services.notification_service.send_notification',side_effect=RuntimeError('retry')):
        with pytest.raises(RuntimeError):refunds.process_event_refund(ID)
    assert not any(name=='hg_ack_event_refund_notice' for name,_ in calls)


@pytest.mark.parametrize('body',[None,[],{}, {'request_id':ID,'reason':'short'},{'request_id':ID,'reason':42}])
def test_refund_endpoint_validates_before_financial_rpc(body):
    with app.test_request_context(json=body),patch.object(events,'get_db') as db:
        _,status=events.request_event_ticket_refund.__wrapped__(ID,TOKEN)
        assert status==400;db.assert_not_called()


def test_refund_endpoint_uses_verified_actor_and_does_not_call_provider():
    with app.test_request_context(json={'request_id':ID,'reason':'Customer requests refund'}),patch.object(events,'get_db') as db,patch.object(payment.http_requests,'post') as post,patch.object(refunds,'wake_event_refund') as wake:
        g.user_id=TOKEN;db.return_value.rpc.return_value={'id':ID,'state':'queued','destination':'paystack'}
        response,status=events.request_event_ticket_refund.__wrapped__(ID,TOKEN)
    assert status==200 and response.json['state']=='queued'
    assert db.return_value.rpc.call_args.args[1]['p_actor_id']==TOKEN;post.assert_not_called();wake.assert_called_once_with(ID)


@pytest.mark.parametrize('code,status',[('42501',403),('P0001',409),('23505',409)])
def test_refund_failures_are_safe_to_retry_without_leaking_db_details(code,status):
    with app.test_request_context(json={'request_id':ID,'reason':'Customer requests refund'}),patch.object(events,'get_db') as db:
        g.user_id=TOKEN;db.return_value.rpc.side_effect=SupabaseError('private database detail',400,{'code':code})
        response,actual=events.request_event_ticket_refund.__wrapped__(ID,TOKEN)
    assert actual==status and 'private database detail' not in response.get_data(as_text=True)


def test_member_notification_recovery_has_one_persisted_message_per_channel():
    from tests.test_notification_preferences_delivery import Db
    from app.services import notification_service as notices
    db=Db()
    with app.app_context(),patch.object(notices,'get_db',return_value=db),patch.object(notices.threading,'Thread') as thread:
        for _ in range(2):
            notices.send_notification('user','event_ticket_refunded',title='Refund',body='Wallet credited',reference_id=ID,reference_type='event_ticket_refund',channels=['email','push','in_app'],strict=True)
    assert len(db.rows['notifications'])==3 and thread.call_count==2


def test_same_charge_webhook_after_refund_does_not_reconfirm_or_send_ticket():
    from app.routes import webhooks
    db=MagicMock();q=db.table.return_value
    q.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':ID,'user_id':None,'payment_status':'refunded','payment_reference':'original-charge','campus_id':TOKEN}
    with patch('app.routes.events.confirm_event_ticket_payment') as confirm:
        assert webhooks._confirm_event_ticket_charge(db,{'ticket_id':ID},'original-charge',{},'paystack')==TOKEN
    confirm.assert_not_called()


def test_unrelated_charge_cannot_hide_behind_refunded_ticket():
    from app.routes import webhooks
    db=MagicMock();q=db.table.return_value
    q.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':ID,'user_id':None,'status':'cancelled','payment_status':'refunded','payment_reference':'original-charge','card_amount_used':1000,'campus_id':TOKEN}
    with patch.object(webhooks,'validate_charge_amount',return_value={'paid_kobo':100000}),patch('app.routes.events.confirm_event_ticket_payment') as confirm,pytest.raises(ValueError):
        webhooks._confirm_event_ticket_charge(db,{'ticket_id':ID},'different-charge',{},'paystack')
    confirm.assert_not_called()


def test_refund_email_checks_refunded_state_and_builds_plain_receipt():
    from app.services import notification_outbox as outbox,notification_service as notices
    db=MagicMock();q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'event_id':ID,'user_id':None,'guest_email':'guest@example.invalid','status':'cancelled','payment_status':'refunded'}
    snapshot={'user_id':None,'email':'guest@example.invalid','name':'Guest','type':'event_ticket_refunded','title':'Refund processed','body':'Original payment refunded','metadata':{}}
    claim={'state':'claimed','token':TOKEN,'key':ID,'channel':'email','payload':{'kind':'event_refund_email','ticket_id':TOKEN,'event_id':ID,'notification':snapshot}}
    db.rpc.side_effect=lambda name,params: claim if name=='hg_claim_notification_dispatch_v2' else True
    with patch.object(outbox,'get_db',return_value=db),patch.object(notices,'_prepare_notification_email',return_value={'provider':'resend'}) as prepare,patch.object(notices,'_deliver_email_attempt',return_value={'state':'accepted','provider':'resend'}):
        assert outbox.dispatch_notification(ID)['state']=='accepted'
    assert prepare.call_args.kwargs['recipient']==snapshot


def test_processed_refund_can_be_verified_when_original_transaction_is_reversed(dispatcher):
    _,claim,charge,response,_,post,_,_=dispatcher;claim.update(state='checking',provider_refund_id='123')
    charge['status']='reversed';response.json.return_value['data']['status']='processed'
    assert refunds.process_event_refund(ID)['state']=='completed';post.assert_not_called()


def test_immediate_wake_runs_with_app_context_and_preserves_durable_id():
    with app.app_context(),patch('threading.Thread') as thread,patch.object(refunds,'process_event_refund') as process:
        refunds.wake_event_refund(ID)
        assert thread.call_args.kwargs['daemon'] is True
        thread.return_value.start.assert_called_once()
        thread.call_args.kwargs['target']()
    process.assert_called_once_with(ID)


def test_immediate_wake_failure_leaves_recovery_to_the_stored_queue():
    with app.app_context(),patch('threading.Thread') as thread,patch.object(refunds,'process_event_refund',side_effect=RuntimeError('retry')):
        refunds.wake_event_refund(ID)
        thread.call_args.kwargs['target']()  # no exception escapes background work


@pytest.mark.parametrize('role,active,status',[('student',True,403),('rider',True,403),('admin',False,403),('admin',True,200),('super_admin',True,200)])
def test_actual_refund_route_authentication_and_staff_roles(role,active,status):
    from app.middleware import auth
    server=Flask(__name__);server.register_blueprint(events.events_bp,url_prefix='/events')
    db=MagicMock();db.auth_get_user.return_value={'id':TOKEN}
    q=db.table.return_value
    for method in ('select','eq','single'):getattr(q,method).return_value=q
    q.execute.return_value={'id':TOKEN,'role':role,'is_active':active,'campus_id':ID}
    db.rpc.return_value={'id':ID,'state':'queued','destination':'paystack'}
    with patch.object(auth,'get_db',return_value=db),patch.object(events,'get_db',return_value=db),patch.object(refunds,'wake_event_refund'):
        response=server.test_client().post(f'/events/{ID}/tickets/{TOKEN}/refund',json={'request_id':ID,'reason':'Customer requests refund','actor_id':'forged'},headers={'Authorization':'Bearer synthetic-local-only'})
    assert response.status_code==status
    if status==403:db.rpc.assert_not_called()
    else:assert db.rpc.call_args.args[1]['p_actor_id']==TOKEN


@pytest.mark.parametrize('body',[None,[],{}, {'review_id':ID,'outcome':'completed','evidence':'Provider log confirms result'},{'review_id':ID,'outcome':'lookup','provider_refund_id':'not-a-number','evidence':'Provider log confirms result'}])
def test_refund_review_cannot_mark_complete_or_skip_provider_validation(body):
    with app.test_request_context(json=body),patch.object(events,'get_db') as db:
        _,status=events.review_event_ticket_refund.__wrapped__(ID,TOKEN)
    assert status==400;db.assert_not_called()


def test_refund_review_uses_route_event_and_verified_actor():
    data={'review_id':ID,'outcome':'lookup','provider_refund_id':'123','evidence':'Paystack confirms this refund ID'}
    with app.test_request_context(json=data),patch.object(events,'get_db') as db:
        g.user_id=TOKEN;db.return_value.rpc.return_value={'state':'processing'}
        assert events.review_event_ticket_refund.__wrapped__(ID,TOKEN).json['state']=='processing'
    assert db.return_value.rpc.call_args.args==('hg_review_event_refund',{'p_actor_id':TOKEN,'p_event_id':ID,'p_id':TOKEN,'p_review_id':ID,'p_outcome':'lookup','p_provider_id':'123','p_evidence':data['evidence']})


def test_known_provider_id_is_saved_for_safe_poll_if_first_receipt_write_fails(dispatcher):
    db,_,_,_,calls,post,_,_=dispatcher;original=db.rpc.side_effect;writes=[]
    def rpc(name,params):
        if name=='hg_finish_event_refund':
            writes.append(dict(params))
            if len(writes)==1:raise RuntimeError('response interrupted')
        return original(name,params)
    db.rpc.side_effect=rpc
    assert refunds.process_event_refund(ID)['state']=='processing'
    post.assert_called_once()
    assert writes[-1]['p_provider_id']=='123' and writes[-1]['p_state']=='processing'


@pytest.mark.parametrize('amount',[None,'not-an-amount'])
def test_invalid_refund_amount_receipt_requires_review(dispatcher,amount):
    _,claim,_,response,_,post,_,_=dispatcher;claim.update(state='checking',provider_refund_id='123')
    response.json.return_value['data']['amount']=amount
    assert refunds.process_event_refund(ID)['state']=='uncertain';post.assert_not_called()
