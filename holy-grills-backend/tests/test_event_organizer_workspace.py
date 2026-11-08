"""Real organizer handlers and middleware; provider calls are controlled."""
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import event_organizers as org,uploads
from app.middleware import auth
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ACTOR='33333333-3333-4333-8333-333333333333';E='44444444-4444-4444-8444-444444444444'
app=Flask(__name__);app.register_blueprint(org.bp,url_prefix='/api/event-organizer')
DRAFT={'request_id':E,'title':'Organizer draft','description':'Description','location':'FUTA','starts_at':'2026-12-01T10:00','ends_at':'2026-12-01T12:00','capacity':50}
def context(method='GET',body=None,query='',role='event_organizer'):
 return app.test_request_context('/?'+query,method=method,json=body)

def setup_actor(role='event_organizer'):
 g.user_id=ACTOR;g.user_role=role;g.campus_id=A

@pytest.mark.parametrize('role',['student','rider','kitchen','community_manager'])
def test_real_middleware_denies_nonorganizer_roles(role):
 db=MagicMock();db.auth_get_user.return_value={'id':ACTOR};db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':ACTOR,'role':role,'is_active':True,'campus_id':A}
 with patch.object(auth,'get_db',return_value=db),patch.object(org,'_rpc') as rpc:
  response=app.test_client().get('/api/event-organizer/events/'+E,headers={'Authorization':'Bearer controlled'})
 assert response.status_code==403;rpc.assert_not_called()

@pytest.mark.parametrize('active,campus',[(False,A),(True,None)])
def test_inactive_or_unscoped_organizer_is_rejected(active,campus):
 db=MagicMock();db.auth_get_user.return_value={'id':ACTOR};db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':ACTOR,'role':'event_organizer','is_active':active,'campus_id':campus}
 with patch.object(auth,'get_db',return_value=db),patch.object(org,'_rpc') as rpc:
  response=app.test_client().get('/api/event-organizer/events/'+E,headers={'Authorization':'Bearer controlled'})
 assert response.status_code==403;rpc.assert_not_called()

@pytest.mark.parametrize('extra',[{'is_published':True},{'organizer_id':B},{'hp_reward':100},{'organizer_amount':999},{'price_naira':10},{'capacity':True},{'ends_at':'2026-01-01T00:00'},{'description':{}},{'image_url':'https://untrusted.invalid/image.png'}])
def test_draft_cannot_smuggle_finalization_fields_or_invalid_inputs(extra):
 with context('POST',{**DRAFT,**extra}),patch.object(org,'_rpc') as rpc:
  setup_actor();response,status=org.create_draft.__wrapped__()
 assert status==400;rpc.assert_not_called()

def test_create_uses_client_intent_uuid_and_validated_wat_fields():
 with context('POST',DRAFT),patch.object(org,'_rpc',return_value={'id':E}) as rpc:
  setup_actor();response,status=org.create_draft.__wrapped__()
 assert status==201;name,body=rpc.call_args.args;assert name=='hg_organizer_event_draft' and body['p_event']==E and body['p_data']['starts_at']=='2026-12-01T10:00:00+01:00' and set(body['p_data'])=={'title','description','location','starts_at','ends_at','capacity','image_url'}

def test_actor_id_is_bound_to_authenticated_request():
 db=MagicMock()
 with context(),patch.object(org,'get_db',return_value=db):setup_actor();org._rpc('helper',{'p_event':E})
 assert db.rpc.call_args.args[1]['p_actor']==ACTOR

@pytest.mark.parametrize('role,expected',[('event_organizer',('organizer_id',ACTOR)),('admin',('campus_id',A)),('super_admin',('campus_id',B))])
def test_list_scope_is_not_browser_role_or_campus_input(role,expected):
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','order','limit','offset'):getattr(q,method).return_value=q
 q.execute.return_value=[]
 with context(query='campus_id='+B),patch.object(org,'get_db',return_value=db):setup_actor(role);assert org.list_owned_events.__wrapped__()[1]==200
 q.eq.assert_called_once_with(*expected)

@pytest.mark.parametrize('body',[{'action':'configure','organizer_id':ACTOR,'tiers':[None]},{'action':'configure','organizer_id':ACTOR,'tiers':[{'id':E,'organizer_amount':-1}]},{'action':'changes_requested','notes':'x'},{'action':'publish_arbitrary'}])
def test_review_invalid_terms_are_rejected_before_writes(body):
 with context('POST',body),patch.object(org,'_rpc') as rpc:setup_actor('admin');assert org.review_event.__wrapped__(E)[1]==400
 rpc.assert_not_called()

def test_owner_cannot_approve_payout_even_through_shared_action_endpoint():
 with context('POST',{'action':'approve'}),patch.object(org,'_rpc') as rpc:setup_actor();assert org.review_payout.__wrapped__(E,E)[1]==403
 rpc.assert_not_called()

def test_server_request_amount_cannot_be_supplied_by_browser():
 data={'request_id':E,'bank_name':'Controlled bank','account_name':'Controlled owner','account_number':'0123456789','amount':999999}
 with context('POST',data),patch.object(org,'_rpc',side_effect=[{'id':E,'state':'pending'},{'event':{'id':E,'title':'Event'}}]) as rpc,patch.object(org,'_notice'):
  setup_actor();assert org.request_payout.__wrapped__(E)[1]==200
 assert set(rpc.call_args_list[0].args[1]['p_data'])=={'bank_name','account_name','account_number'} and rpc.call_args_list[0].args[1]['p_request']==E

def test_wrong_event_qr_never_reaches_admission():
 with context('POST',{'qr_token':f'hg-event:{B}:{E}'}),patch.object(org,'_rpc',return_value={'event':{'campus_id':A}}),patch.object(org,'admit_event_ticket') as admit:
  setup_actor();assert org.organizer_checkin.__wrapped__(E)[1]==400
 admit.assert_not_called()

def test_valid_ticket_checkin_uses_authorized_event_campus_and_actor():
 with context('POST',{'qr_token':f'hg-event:{E}:{ACTOR}'}),patch.object(org,'_rpc',return_value={'event':{'campus_id':A}}),patch.object(org,'admit_event_ticket',return_value={'completed':True,'replayed':True}) as admit:
  setup_actor();response,status=org.organizer_checkin.__wrapped__(E)
 assert status==200 and response.json['replayed'];admit.assert_called_once_with(E,ACTOR,ACTOR,None,A)

def test_attendee_export_refuses_truncation():
 with context(),patch.object(org,'_rpc',return_value=[{'ticket_id':'controlled'}]*500):setup_actor();response,status=org.export_attendees.__wrapped__(E)
 assert status==413 and 'attendees' not in response.json

@pytest.mark.parametrize('marker,expected',[('HG_ORGANIZER_ACCESS',403),('HG_ORGANIZER_NOT_FOUND',404),('HG_ORGANIZER_BALANCE_CHANGED',409),('HG_ORGANIZER_BANK_INVALID',400)])
def test_errors_are_centralized_and_do_not_leak_sql(marker,expected):
 with app.app_context():response,status=org._failure(SupabaseError(marker+' private SQL detail',400,{}))
 assert status==expected and 'private SQL' not in response.json['error']

def test_cloudinary_organizer_event_folder_is_owned_and_other_folders_stay_restricted():
 app.config.update(CLOUDINARY_CLOUD_NAME='unit-test-cloud',CLOUDINARY_API_KEY='unit-test-key',CLOUDINARY_API_SECRET='unit-test-signing-value')
 for folder,expected in [('events','event_organizers/'+ACTOR),('storefront','profile_photos/'+ACTOR)]:
  with context('POST',{'folder':folder}):setup_actor();response,status=uploads.upload_signature.__wrapped__()
  assert status==200 and response.json['folder']==expected

@pytest.mark.parametrize('status,expected',[('approved',200),('draft',409)])
def test_owned_venue_qr_requires_approval_and_stays_local(status,expected):
 db=MagicMock()
 with context('POST',{}),patch.object(org,'_rpc',return_value={'event':{'review_status':status}}),patch.object(org,'get_db',return_value=db):
  setup_actor();response,actual=org.organizer_door_qr.__wrapped__(E)
 assert actual==expected
 if expected==200:
  assert response.json['qr_image'].startswith('data:image/png;base64,') and response.json['qr_payload'].startswith('hg-event:'+E+':')
  assert db.table.call_args.args[0]=='event_door_tokens'
 else:db.table.assert_not_called()

def test_review_notice_targets_own_campus_staff_and_opens_exact_event():
 db=MagicMock();db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value=[{'id':ACTOR,'role':'admin','campus_id':A},{'id':E,'role':'super_admin','campus_id':None},{'id':B,'role':'admin','campus_id':B}]
 event={'id':E,'title':'Controlled event','campus_id':A,'organizer_id':ACTOR,'review_status':'submitted','updated_at':'2026-11-08T12:00:00Z'}
 with app.app_context(),patch.object(org,'get_db',return_value=db),patch.object(org,'send_notification') as notify:
  org._notice(event,'event_review_submitted');org._notice(event,'event_review_submitted')
 assert notify.call_count==4
 assert {call.args[0] for call in notify.call_args_list}=={ACTOR,E}
 assert all(call.kwargs['action_url']=='/event-manager?event='+E for call in notify.call_args_list)
 assert len({call.kwargs['reference_id'] for call in notify.call_args_list})==1

@pytest.mark.parametrize('campus',[A,None])
def test_super_admin_draft_scope_comes_from_validated_header(campus):
 with app.test_request_context(method='POST',json=DRAFT,headers={'X-Campus-ID':campus} if campus else {}),patch.object(org,'_rpc',return_value={'id':E}) as rpc:
  setup_actor('super_admin');g.campus_id=None
  assert org.create_draft.__wrapped__()[1]==201
 assert rpc.call_args.args[1]['p_data']['campus_id']==campus
