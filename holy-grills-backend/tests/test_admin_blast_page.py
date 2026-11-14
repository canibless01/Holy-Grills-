from flask import Flask,g
from unittest.mock import MagicMock,patch
import pytest
from app.routes import notifications as route
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ID='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
class Query:
 def __init__(self,rows):self.rows=rows;self.filters=[]
 def select(self,*args):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def single(self):return self
 def execute(self):return next((r for r in self.rows if all(r.get(k)==v for k,v in self.filters)),None)
class DB:
 def __init__(self,rows):self.rows=rows
 def table(self,name):assert name=='notification_blasts';return Query(self.rows)
@pytest.mark.parametrize('role,scope,campus,status',[('admin',None,A,200),('admin',None,B,404),('admin',None,None,404),('super_admin',A,B,404),('super_admin',A,None,404),('super_admin',None,B,200),('super_admin',None,None,200)])
def test_analytics_uses_customer_rls_client_and_exact_campus(role,scope,campus,status):
 db=DB([{'id':ID,'campus_id':campus,'recipient_count':10,'metadata':{'open_count':2,'click_count':1}}])
 with app.test_request_context(headers={'X-Campus-ID':scope} if scope else {}),patch.object(route,'get_user_client',return_value=db),patch.object(route,'get_db') as service:
  g.user_id=ID;g.user_role=role;g.campus_id=A;response,actual=route.get_blast_analytics.__wrapped__(ID)
 assert actual==status;service.assert_not_called()
 if actual==200:assert response.json['open_rate']==20 and response.json['click_rate']==10
@pytest.mark.parametrize('entry',[None,True,-5,'bad'])
def test_malformed_analytics_totals_are_bounded(entry):
 db=DB([{'id':ID,'campus_id':A,'recipient_count':entry,'metadata':{'open_count':entry,'click_count':entry}}])
 with app.test_request_context(),patch.object(route,'get_user_client',return_value=db):
  g.user_id=ID;g.user_role='admin';g.campus_id=A;response,status=route.get_blast_analytics.__wrapped__(ID)
 assert status==200 and response.json['recipient_count']==0 and response.json['open_rate']==0
@pytest.mark.parametrize('fn',[route.get_blast,route.cancel_blast,route.retry_blast])
def test_hidden_campus_cannot_be_read_cancelled_or_retried(fn):
 db=DB([{'id':ID,'campus_id':B,'status':'pending'}])
 with app.test_request_context(),patch.object(route,'get_user_client',return_value=db),patch.object(route,'send_blast') as send:
  g.user_id=ID;g.user_role='admin';g.campus_id=A;_,status=fn.__wrapped__(ID)
 assert status==404;send.assert_not_called()
def test_in_app_preview_does_not_wait_for_email():
 from tests.test_rich_blast_contracts import DB as FixtureDB,USER,A as CAMPUS,INTENT
 db=FixtureDB({'profiles':[{'id':USER,'campus_id':CAMPUS,'email':'admin@example.invalid'}]})
 with app.test_request_context(method='POST',json={'title':'Title','body':'Body','channels':['in_app'],'request_id':INTENT}),patch.object(route,'get_user_client',return_value=db),patch.object(route,'send_blast',return_value={'sent_to':1}),patch.object(route,'_await_email_delivery') as wait:
  g.user_id=USER;g.user_role='admin';g.campus_id=CAMPUS;response,status=route.send_test_blast.__wrapped__()
 assert status==200 and response.json['email'] is None;wait.assert_not_called()

def test_legacy_deliverability_cannot_send_to_foreign_email():
 from tests.test_rich_blast_contracts import DB as FixtureDB,USER,A as CAMPUS
 db=FixtureDB({'profiles':[{'id':USER,'campus_id':CAMPUS,'email':'admin@example.invalid'}]})
 with app.test_request_context(method='POST',json={'test_email':'foreign@example.invalid'}),patch.object(route,'get_user_client',return_value=db),patch.object(route,'send_blast') as send:
  g.user_id=USER;g.user_role='admin';g.campus_id=CAMPUS;_,status=route.test_email_deliverability.__wrapped__()
 assert status==403;send.assert_not_called();assert not db.writes

@pytest.mark.parametrize('role,scope,target_campus,status',[('admin',None,A,200),('admin',None,B,404),('super_admin',A,B,404),('super_admin',None,B,200)])
def test_subscription_sync_cannot_inspect_or_mutate_another_campus(role,scope,target_campus,status):
 from app.routes import admin
 from tests.test_rich_blast_contracts import DB as FixtureDB
 db=FixtureDB({'profiles':[{'id':ID,'campus_id':target_campus,'email':'target@example.invalid','is_active':True}]})
 with app.test_request_context(method='POST',json={'user_id':ID},headers={'X-Campus-ID':scope} if scope else {}),patch.object(admin,'get_db',return_value=db),patch('app.services.onesignal_email.ensure_email_subscription',return_value=True) as ensure:
  g.user_id=ID;g.user_role=role;g.campus_id=A;_,actual=admin.backfill_email_subscriptions.__wrapped__()
 assert actual==status
 if status==404:ensure.assert_not_called()

@pytest.mark.parametrize('body',[{'user_id':False},{'email':25},{'limit':True},{'offset':-1}])
def test_subscription_sync_bad_input_never_launches_work(body):
 from app.routes import admin
 with app.test_request_context(method='POST',json=body),patch.object(admin.threading,'Thread') as thread:
  g.user_id=ID;g.user_role='admin';g.campus_id=A;_,status=admin.backfill_email_subscriptions.__wrapped__()
 assert status==400;thread.assert_not_called()


def test_tracking_toggle_survives_validated_create_and_replay():
 from tests.test_rich_blast_contracts import DB as FixtureDB,USER,A as CAMPUS,INTENT
 db=FixtureDB();body={'title':'Tracked email','body':'Body','channels':['email'],'request_id':INTENT,'tracking_enabled':True}
 for expected in (201,200):
  with app.test_request_context(method='POST',json=body),patch.object(route,'get_user_client',return_value=db),patch.object(route,'resolve_write_campus',return_value=CAMPUS),patch.object(route,'send_blast',return_value={'sent_to':1}):
   g.user_id=USER;g.user_role='admin';g.campus_id=CAMPUS;response,status=route.create_blast.__wrapped__()
  assert status==expected and response.json['blast']['tracking_enabled'] is True
 assert len(db.rows['notification_blasts'])==1
