"""Event operations: actual middleware/handlers, with boundaries controlled."""
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import event_organizers as org,webhooks
from app.middleware import auth
from app.db import SupabaseError
from app.messages import MSG
from app.services.notification_preferences import category_for_notification
A='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222';R='33333333-3333-4333-8333-333333333333';T='44444444-4444-4444-8444-444444444444'
app=Flask(__name__);app.register_blueprint(org.bp,url_prefix='/api/event-organizer')
BASE={'request_id':R,'action':'cancel','reason':'The host has cancelled this event.','expected_updated_at':'2026-11-09T10:00:00Z'}

def call(body,result=None):
 with app.test_request_context(method='POST',json=body),patch.object(org,'_rpc',return_value=result or {'id':R,'action':body.get('action') if isinstance(body,dict) else None}) as rpc,patch.object(org,'_wake_event_operation') as wake:
  g.user_id=A;g.user_role='admin';g.campus_id=A
  response,status=org.change_event_operation.__wrapped__(E)
 return response,status,rpc,wake

@pytest.mark.parametrize('body',[None,[],{},dict(BASE,request_id='bad'),dict(BASE,action='publish'),dict(BASE,reason='short'),dict(BASE,campus_id=A),dict(BASE,action='reschedule',starts_at='not-date',ends_at='2027-12-01T12:00',location='Hall')])
def test_invalid_operation_never_reaches_database(body):
 _,status,rpc,wake=call(body)
 assert status==400;rpc.assert_not_called();wake.assert_not_called()

def test_cancel_intent_and_central_copy_are_server_bound():
 _,status,rpc,wake=call(BASE)
 assert status==200
 name,body=rpc.call_args.args
 assert name=='hg_change_event_operation' and body['p_request']==R and body['p_event']==E
 assert body['p_data']['_copy']['event_cancelled_body']==MSG.EVENT_CANCELLED_NOTICE_BODY
 wake.assert_called_once_with(E)

def test_reschedule_normalizes_wat_and_preserves_reason():
 _,status,rpc,_=call({**BASE,'action':'reschedule','starts_at':'2027-12-01T10:00','ends_at':'2027-12-01T12:00','location':'FUTA hall'})
 assert status==200 and rpc.call_args.args[1]['p_data']['starts_at']=='2027-12-01T10:00:00+01:00'

@pytest.mark.parametrize('role',['student','event_organizer','kitchen','rider','community_manager'])
def test_real_middleware_prevents_nonadmin_event_financial_changes(role):
 db=MagicMock();db.auth_get_user.return_value={'id':A};db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':A,'role':role,'campus_id':A,'is_active':True}
 with patch.object(auth,'get_db',return_value=db),patch.object(org,'_rpc') as rpc:
  response=app.test_client().post('/api/event-organizer/events/'+E+'/change',json=BASE,headers={'Authorization':'Bearer controlled'})
 assert response.status_code==403;rpc.assert_not_called()

@pytest.mark.parametrize('marker,key,status',[('HG_EVENT_ALREADY_CANCELLED','EVENT_ALREADY_CANCELLED',409),('HG_EVENT_ADMISSION_STARTED','EVENT_CHANGE_ADMISSION_STARTED',409),('HG_EVENT_CHANGE_UNCHANGED','EVENT_CHANGE_UNCHANGED',400),('Ticket financial breakdown invalid','EVENT_CHANGE_FINANCIAL_REVIEW',409)])
def test_recoverable_errors_are_central_and_hide_sql(marker,key,status):
 with app.app_context():response,actual=org._failure(SupabaseError(marker+' private SQL detail',400,{}))
 assert actual==status and response.json['error']==getattr(MSG,key)

@pytest.mark.parametrize('kind',['event_cancelled','event_rescheduled'])
def test_operational_notices_follow_order_preferences_not_marketing(kind):assert category_for_notification(kind)=='order_updates'

def test_verified_late_charge_for_cancelled_event_reaches_atomic_refund_path():
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','single'):getattr(q,method).return_value=q
 q.execute.side_effect=[{'id':T,'event_id':E,'status':'cancelled','payment_status':'expired','card_amount_used':100,'payment_reference':'original','campus_id':A},{'metadata':{'lifecycle_status':'cancelled'}}]
 with patch.object(webhooks,'validate_charge_amount',return_value={'paid_kobo':10000}),patch('app.routes.events.confirm_event_ticket_payment') as confirm:
  assert webhooks._confirm_event_ticket_charge(db,{'ticket_id':T},'original',{},'paystack')==A
 confirm.assert_called_once()

def test_expired_charge_for_uncancelled_event_does_not_reissue_ticket():
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','single'):getattr(q,method).return_value=q
 q.execute.side_effect=[{'id':T,'event_id':E,'status':'cancelled','payment_status':'expired','card_amount_used':100,'payment_reference':'original','campus_id':A},{'metadata':{}}]
 with patch.object(webhooks,'validate_charge_amount',return_value={'paid_kobo':10000}),patch('app.routes.events.confirm_event_ticket_payment') as confirm,pytest.raises(ValueError):
  webhooks._confirm_event_ticket_charge(db,{'ticket_id':T},'original',{},'paystack')
 confirm.assert_not_called()
