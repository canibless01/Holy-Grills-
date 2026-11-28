"""Group registration validates each recipient, private recovery and provider binding."""
from copy import deepcopy
from uuid import uuid4
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.services import event_groups as groups
from app.messages import MSG
from app.utils.event_ticket_access import valid_ticket_access
E='11111111-1111-4111-8111-111111111111';G='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
CONTACT={'name':'Buyer','email':'buyer@example.invalid','phone':'08012345678'}
FIELDS=[{'name':'department','label':'Department','type':'select','options':['Computing','Engineering'],'required':True},{'name':'permission','label':'Agree','type':'checkbox','required':True}]
ROSTER=[{'name':name,'email':email,'phone':'08012345678','tier_id':E,'answers':{'department':dept,'permission':True}} for name,email,dept in [('First','first@example.invalid','Computing'),('Second','second@example.invalid','Engineering')]]

def app():
 a=Flask(__name__);a.config.update(SECRET_KEY='controlled-signing-only',FRONTEND_URL='https://holygrills.online',PAYSTACK_SECRET_KEY='controlled-never-network');return a

def test_all_question_types_remain_separate_per_attendee():
 fields=[{'name':kind,'type':kind,'options':['A','B'],'required':True} for kind in ('text','textarea','select','radio','multiselect','checkbox','date','email','number')]
 answers={'text':'First','textarea':'First paragraph\n\nSecond paragraph','select':'A','radio':'B','multiselect':['A','B'],'checkbox':True,'date':'2026-11-23','email':'answer@example.invalid','number':'2.5'}
 rows=deepcopy(ROSTER)
 rows[0]['answers']=answers;rows[1]['answers']={**answers,'text':'Second','radio':'A'}
 result=groups.clean_attendees(rows,fields)
 assert result[0]['answers']==answers and result[1]['answers']['text']=='Second'
 assert result[0]['answers']['radio']=='B' and result[1]['answers']['radio']=='A'

@pytest.mark.parametrize('change', ['missing','duplicate','invalid_type','extra_people','bad_tier','bad_contact'])
def test_invalid_attendees_are_actionable_before_any_rpc(change):
 rows=deepcopy(ROSTER)
 if change=='missing':rows[1]['answers']={}
 if change=='duplicate':rows[1]['email']=rows[0]['email'].upper()
 if change=='invalid_type':rows[1]['answers']['permission']='true'
 if change=='extra_people':rows*=6
 if change=='bad_tier':rows[1]['tier_id']='not-an-id'
 if change=='bad_contact':rows[1]['phone']='123'
 with pytest.raises(ValueError):groups.clean_attendees(rows,FIELDS)


def test_single_friend_purchase_is_allowed_without_a_shared_hp_pool():
 assert len(groups.clean_attendees(ROSTER[:1],FIELDS))==1
 with app().test_request_context(),patch.object(groups,'get_db') as db:
  g.user_id=U
  with pytest.raises(ValueError):groups.create({'id':E,'registration_fields':FIELDS},{'attendees':ROSTER,'use_hp':True},CONTACT)
 db.assert_not_called()


def test_existing_committed_booking_replays_before_changed_questions_or_promo():
 db=MagicMock();saved={}
 def rpc(name,body):
  if name=='hg_event_group_by_intent':return saved or None
  assert name=='hg_create_event_group'
  saved.update(id=G,event_id=E,fingerprint=body['p_fingerprint'],buyer_user_id=U,buyer_email=CONTACT['email'])
  return saved
 db.rpc.side_effect=rpc
 body={'attendees':ROSTER,'payment_method':'wallet','idempotency_key':str(uuid4())}
 with app().test_request_context(),patch.object(groups,'get_db',return_value=db):
  g.user_id=U
  first=groups.create({'id':E,'registration_fields':FIELDS},body,CONTACT)
  replay=groups.create({'id':E,'registration_fields':[{'name':'new_required','required':True,'type':'text'}]},body,CONTACT)
  assert first['id']==replay['id']==G
  with pytest.raises(ValueError,match='changed'):groups.create({'id':E,'registration_fields':FIELDS},{**body,'attendees':ROSTER[:1]},CONTACT)
 assert sum(call.args[0]=='hg_create_event_group' for call in db.rpc.call_args_list)==1


def test_private_buyer_proof_is_group_bound_and_uuid_or_matching_email_is_insufficient():
 group={'id':G,'event_id':E,'buyer_user_id':U,'buyer_email':CONTACT['email']}
 with app().test_request_context():
  g.user_id=None;token=groups.access_token(group)
  assert groups.may_read(group,token)
  assert not groups.may_read(group,CONTACT['email'])
  assert not groups.may_read({**group,'id':E},token)
  assert not groups.may_read({**group,'buyer_email':'other@example.invalid'},token)
  g.user_id=U;assert groups.may_read(group)


def group():return {'id':G,'event_id':E,'buyer_user_id':U,'buyer_email':CONTACT['email'],'payment_reference':'HG-EVGRP-CONTROLLED','payment_status':'pending','card_amount':200,'wallet_amount':100,'total':300,'tickets':[{'id':U,'event_id':E,'guest_name':'First','guest_email':'first@example.invalid','price_naira':300,'discount_amount':0,'status':'pending_payment','payment_status':'pending'}]}

def test_unpaid_snapshot_never_issues_entry_access():
 with app().test_request_context():
  value=groups.snapshot(group());assert 'access_token' not in value['tickets'][0]
  value=groups.snapshot({**group(),'tickets':[{**group()['tickets'][0],'status':'confirmed','payment_status':'paid'}]})
  assert valid_ticket_access(value['tickets'][0]['access_token'],{**group()['tickets'][0],'user_id':None},None)

@pytest.mark.parametrize('mutate',[lambda t:t.update(currency='USD'),lambda t:t.update(amount=10000),lambda t:t.update(amount=10000,requested_amount=20000),lambda t:t.update(status='pending'),lambda t:t['metadata'].update(group_id=E),lambda t:t['metadata'].update(event_id=G),lambda t:t['metadata'].update(type='event_ticket_payment')])
def test_forged_or_underpaid_group_charge_cannot_mark_tickets_paid(mutate):
 charge={'status':'success','amount':20000,'currency':'NGN','metadata':{'type':'event_group_payment','group_id':G,'event_id':E}}
 mutate(charge)
 with app().test_request_context(),patch.object(groups,'get_db') as db:
  with pytest.raises(ValueError):groups.confirm(group(),group()['payment_reference'],charge)
 db.assert_not_called()


def test_correct_payment_confirms_one_group_and_dispatches_each_paid_ticket():
 db=MagicMock();db.rpc.return_value={**group(),'tickets':[{'id':E,'payment_status':'paid'},{'id':G,'payment_status':'paid'}]}
 charge={'status':'success','amount':20000,'currency':'NGN','metadata':{'type':'event_group_payment','group_id':G,'event_id':E}}
 with app().test_request_context(),patch.object(groups,'get_db',return_value=db),patch('app.services.notification_outbox.start_ticket_email_dispatch') as send:
  groups.confirm(group(),group()['payment_reference'],charge)
 assert db.rpc.call_args.args[0]=='hg_pay_event_group' and send.call_count==3


def test_gateway_callback_is_first_party_and_initialization_uses_aggregate_remainder():
 db=MagicMock()
 with app().test_request_context(),patch.object(groups,'get_db',return_value=db),patch('app.services.payment_service.initialize_payment',return_value={'authorization_url':'https://checkout.paystack.com/controlled'}) as payment:
  result=groups.initialize(group(),'https://evil.example')
 assert payment.call_args.kwargs['amount_naira']==200
 assert payment.call_args.kwargs['callback_url']==f'https://holygrills.online/events/{E}/group/{G}'
 assert result['authorization_url'].startswith('https://checkout.paystack.com/')


def test_reference_owned_bank_payment_with_missing_metadata_stays_out_of_wallet_topup():
 from app.routes import webhooks
 from uuid import UUID
 row={**group(),'id':G,'payment_reference':'HG-EVGRP-'+G.replace('-','')}
 charge={'reference':row['payment_reference'],'status':'success','currency':'NGN','amount':20000,'metadata':None}
 with app().test_request_context(),patch.object(groups,'read',return_value=row) as read,patch.object(groups,'confirm') as confirm,patch.object(webhooks,'get_db',return_value=MagicMock()),patch.object(webhooks,'credit_wallet') as credit:
  webhooks._handle_charge_success(charge)
 read.assert_called_once_with(G);confirm.assert_called_once_with(row,row['payment_reference'],charge);credit.assert_not_called()
 with app().test_request_context(),patch.object(groups,'get_db',return_value=MagicMock()) as db,patch('app.services.notification_outbox.start_ticket_email_dispatch'):
  db.return_value.rpc.return_value={'id':G,'tickets':[]}
  groups.confirm(row,row['payment_reference'],charge)
 assert db.return_value.rpc.call_args.args[0]=='hg_pay_event_group'


def test_individual_webhook_cannot_settle_a_group_child_separately():
 from app.routes import webhooks
 db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':E,'group_id':G}
 with pytest.raises(ValueError,match='Group tickets'):webhooks._confirm_event_ticket_charge(db,{'ticket_id':E},'child-reference',{},'paystack')


def test_create_controller_recovers_before_release_or_visibility_changes():
 import inspect
 from app.routes import events
 body={'buyer':CONTACT,'attendees':ROSTER,'payment_method':'card','idempotency_key':str(uuid4())}
 saved={**group(),'payment_status':'paid'}
 with app().test_request_context(method='POST',json=body),patch.object(groups,'recover',return_value=saved),patch.object(groups,'snapshot',return_value={'id':G,'payment_status':'paid'}),patch.object(events,'get_user_client') as event_read,patch.object(events,'is_feature_enabled',return_value=False),patch.object(groups,'create') as create:
  g.user_id=None
  response,status=inspect.unwrap(events.create_group_booking)(E)
 assert status==200 and response.json['id']==G
 event_read.assert_not_called();create.assert_not_called()

@pytest.mark.parametrize('error,status', [('HG_GROUP_PRICE_CHANGED',409),('Promo code usage limit reached',400),('Tier at capacity',409),('Insufficient wallet balance',400),('HG_GROUP_BUYER_UNAVAILABLE',403)])
def test_controller_known_failures_allow_correction_without_an_uncertain_payment_loop(error,status):
 import inspect
 from app.routes import events
 from app.db import SupabaseError
 db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':E,'is_published':True,'campus_id':None}
 body={'buyer':CONTACT,'attendees':ROSTER,'payment_method':'card','idempotency_key':str(uuid4())}
 with app().test_request_context(method='POST',json=body),patch.object(groups,'recover',return_value=None),patch.object(groups,'create',side_effect=SupabaseError(error,400,{})),patch.object(events,'get_user_client',return_value=db),patch.object(events,'_get_campus_id',return_value=None),patch.object(events,'is_feature_enabled',return_value=True):
  g.user_id=None
  response,actual=inspect.unwrap(events.create_group_booking)(E)
 assert actual==status
 if error=='HG_GROUP_PRICE_CHANGED':assert response.json['pricing_changed'] is True


def test_group_payment_rechecks_completed_booking_instead_of_starting_another_charge():
 import inspect
 from app.routes import events
 with app().test_request_context(method='POST',json={}),patch.object(events,'_owned_event_group',return_value={**group(),'payment_status':'paid'}),patch.object(groups,'initialize') as initialize:
  response,status=inspect.unwrap(events.pay_group_booking)(E,G)
 assert status==200 and response.json['payment_status']=='paid';initialize.assert_not_called()


def test_buyer_receipt_has_private_cross_device_recovery_and_escaped_event_content():
 from urllib.parse import urlparse,parse_qs
 from html import unescape
 import re
 value={**group(),'buyer_name':'Buyer','payment_status':'paid'}
 db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'title':'<script>event</script>'}
 with app().test_request_context(),patch.object(groups,'get_db',return_value=db),patch('app.services.notification_service.get_email_provider',return_value='resend'):
  g.user_id=None
  email=groups.prepare_receipt(value)
  assert email['to_email']==CONTACT['email'] and email['transactional'] is True
  assert '<script>event</script>' not in email['html_body'] and '&lt;script&gt;' in email['html_body']
  links=re.findall(r'href="([^"]+)"',email['html_body'])
  link=next(unescape(link) for link in links if f'/events/{E}/group/{G}?' in link)
  token=parse_qs(urlparse(link).query)['access'][0]
  assert groups.may_read(value,token)
  assert not groups.may_read({**value,'id':E},token)


def test_buyer_receipt_uses_shared_durable_email_dispatch_without_marketing_opt_in():
 from app.services import notification_outbox as outbox
 value={**group(),'buyer_name':'Buyer','payment_status':'paid'}
 db=MagicMock()
 def rpc(name,args):
  if name=='hg_claim_notification_dispatch_v2':return {'state':'claimed','channel':'email','token':U,'key':G,'payload':{'kind':'event_group_email','group_id':G,'event_id':E,'notification':{'email':CONTACT['email'],'type':'event_group_booked','metadata':{}}}}
  return True
 db.rpc.side_effect=rpc
 prepared={'to_email':CONTACT['email'],'transactional':True}
 with app().test_request_context(),patch.object(outbox,'get_db',return_value=db),patch.object(groups,'read',return_value=value),patch.object(groups,'prepare_receipt',return_value=prepared),patch('app.services.notification_service._deliver_email_attempt',return_value={'state':'accepted','provider':'resend'}) as send,patch.object(outbox,'effective_preferences') as prefs:
  assert outbox.dispatch_notification(G)['state']=='accepted'
 send.assert_called_once_with(prepared);prefs.assert_not_called()
 assert any(call.args[0]=='hg_begin_notification_dispatch' for call in db.rpc.call_args_list)


def test_email_only_recipients_use_purchaser_contact_without_inventing_friends_names():
 rows=[{'email':'friend@example.invalid','answers':{}},{'email':CONTACT['email'],'answers':{}}]
 result=groups.clean_attendees(rows,[],booking_contact=CONTACT)
 assert result[0]['email']=='friend@example.invalid' and result[0]['name']=='friend@example.invalid'
 assert result[0]['phone']==CONTACT['phone']
 assert result[1]['name']==CONTACT['name']
 with pytest.raises(ValueError):groups.clean_attendees([{'email':'invalid'}],[],booking_contact=CONTACT)


def test_shared_answers_validated_once_and_booking_contact_annotated_on_each_ticket():
 body={'attendees':[{'email':'friend@example.invalid','tier_id':E},{'email':'second@example.invalid','tier_id':E}],
       'registration_answers':{'department':'Computing','permission':True},'booking_notes':'2 vegetarian\n3 regular',
       'payment_method':'card','idempotency_key':str(uuid4())}
 db=MagicMock()
 with app().test_request_context(),patch.object(groups,'get_db',return_value=db):
  g.user_id=None
  groups.create({'id':E,'registration_fields':FIELDS},body,CONTACT,lookup=False)
  rows=db.rpc.call_args.args[1]['p_attendees']
  assert len(rows)==2 and all(row['answers']==body['registration_answers'] for row in rows)
  assert all(row['registration_context']=={'scope':'group','answered_by':'Buyer','notes':body['booking_notes']} for row in rows)
  body['registration_answers']={}
  with pytest.raises(groups.GroupAnswersError):groups.create({'id':E,'registration_fields':FIELDS},body,CONTACT,lookup=False)


def test_group_shared_answers_and_quantities_are_bound_to_recovery_intent():
 body={'attendees':[{'email':'friend@example.invalid'}],'registration_answers':{'meal':'regular'},'booking_notes':'2 meals','payment_method':'card','idempotency_key':str(uuid4())}
 with app().test_request_context():
  g.user_id=None
  first=groups._plan(E,body,CONTACT)['fingerprint']
  assert first!=groups._plan(E,{**body,'booking_notes':'3 meals'},CONTACT)['fingerprint']
  assert first!=groups._plan(E,{**body,'registration_answers':{'meal':'vegetarian'}},CONTACT)['fingerprint']
  with pytest.raises(ValueError):groups._plan(E,{**body,'booking_notes':'x'*5001},CONTACT)
