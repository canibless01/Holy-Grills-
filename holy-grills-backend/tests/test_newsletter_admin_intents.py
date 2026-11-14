from flask import Flask,g
from unittest.mock import MagicMock,patch
import pytest
from app.routes import storefront as sf
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';C='22222222-2222-4222-8222-222222222222';R='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
@pytest.mark.parametrize('role,campus,body,status',[('admin',None,{'subject':'Hi','body':'Body'},403),('super_admin',C,{'subject':'Hi','body':'Body'},400),('super_admin',C,{'subject':'Hi','body':'Body','campus_id':'bad'},400),('admin',C,{'subject':'','body':'Body'},400),('admin',C,{'subject':'Hi','body':'Body','request_id':True},400)])
def test_campaign_validation_and_explicit_target(role,campus,body,status):
 with app.test_request_context(method='POST',json=body),patch.object(sf,'get_db') as db:
  g.user_id=A;g.user_role=role;g.campus_id=campus;_,actual=sf.create_newsletter_campaign.__wrapped__()
 assert actual==status;db.assert_not_called()
def test_create_uses_server_actor_and_campus_and_replay():
 db=MagicMock();db.rpc.return_value={'campaign':{'id':R,'status':'cancelled'},'replayed':True}
 with app.test_request_context(method='POST',json={'request_id':R,'subject':'  Hi\nthere ','body':' First\n\nSecond ','campus_id':A,'all_campuses':True}),patch.object(sf,'get_db',return_value=db):
  g.user_id=A;g.user_role='admin';g.campus_id=C;response,status=sf.create_newsletter_campaign.__wrapped__()
 assert status==200 and response.json['campaign']['status']=='cancelled';db.rpc.assert_called_once_with('hg_queue_newsletter_campaign',{'p_actor':A,'p_request':R,'p_campus':C,'p_subject':'Hi there','p_body':'First\n\nSecond'})
@pytest.mark.parametrize('role,header,expected',[('admin',A,C),('super_admin',A,A),('super_admin',None,None)])
def test_newsletter_lists_follow_scope(role,header,expected):
 db=MagicMock();q=db.table.return_value
 for key in ('select','eq','is_','order','limit','offset'):getattr(q,key).return_value=q
 q.execute.return_value=[]
 with app.test_request_context(headers={'X-Campus-ID':header} if header else {}),patch.object(sf,'get_user_client',return_value=db):
  g.user_id=A;g.user_role=role;g.campus_id=C;sf.newsletter_list.__wrapped__();sf.list_newsletter_campaigns.__wrapped__()
 if expected:assert q.eq.call_args_list and all(call.args==('campus_id',expected) for call in q.eq.call_args_list)
 else:q.eq.assert_not_called()
def test_cancel_scope_and_server_actor():
 db=MagicMock();db.rpc.return_value={'campaign':{'id':R,'status':'cancelled'},'replayed':True}
 with app.test_request_context(method='POST',headers={'X-Campus-ID':C}),patch.object(sf,'get_db',return_value=db):
  g.user_id=A;g.user_role='super_admin';g.campus_id=A;_,status=sf.cancel_newsletter_campaign.__wrapped__(R)
 assert status==200;db.rpc.assert_called_once_with('hg_cancel_newsletter_campaign',{'p_actor':A,'p_campaign':R,'p_scope':C})


def test_newsletter_is_marketing_even_without_one_click_api_url():
 from app.services import newsletter_service
 with patch('app.utils.email.send_email_routed',return_value=True) as send:
  assert newsletter_service._default_sender('a@example.invalid','A','Subject','<p>Body</p>',None)
 send.assert_called_once_with('a@example.invalid','A','Subject','<p>Body</p>',provider='resend',headers=None,transactional=False,receipt={})

@pytest.mark.parametrize('role',['student','event_organizer','community_manager','kitchen','rider'])
@pytest.mark.parametrize('method,path',[('GET','/newsletter'),('POST','/newsletter/campaigns'),('POST',f'/newsletter/campaigns/{R}/cancel')])
def test_nonstaff_cannot_reach_admin_newsletter(role,method,path):
 from app.middleware import auth
 secured=Flask(__name__);secured.register_blueprint(sf.storefront_bp,url_prefix='/api/storefront')
 db=MagicMock();db.auth_get_user.return_value={'id':A};q=db.table.return_value
 for name in ('select','eq','single'):getattr(q,name).return_value=q
 q.execute.return_value={'id':A,'role':role,'campus_id':C,'is_active':True}
 with patch.object(auth,'get_db',return_value=db),patch.object(sf,'get_db') as writes:
  response=secured.test_client().open('/api/storefront'+path,method=method,json={'subject':'Subject','body':'Body'},headers={'Authorization':'Bearer synthetic'})
 assert response.status_code==403;writes.assert_not_called()
