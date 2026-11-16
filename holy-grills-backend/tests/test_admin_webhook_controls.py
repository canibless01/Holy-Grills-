"""Actual administrative webhook handlers, controlled DB/provider boundaries."""
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask,g
from app.routes import admin,webhooks
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';ID='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
def database(rows):
 db=MagicMock();q=db.table.return_value
 for m in ('select','eq','or_','gte','lt','order','limit','offset','single','update'):getattr(q,m).return_value=q
 q.execute.return_value=rows
 return db,q

def listing(query='',rows=None,role='admin'):
 db,q=database(rows or [])
 with app.test_request_context('/?'+query),patch.object(admin,'get_db',return_value=db):
  g.user_role=role;g.campus_id=A
  response,status=admin.list_webhook_events.__wrapped__()
 return response,status,q

@pytest.mark.parametrize('query',['limit=bad','limit=0','offset=-1','from_date=2026-02-30','from_date=2026-11-08&to_date=2026-11-07','from_date=0001-01-01'])
def test_bad_dates_paging_never_query(query):
 _,status,q=listing(query);assert status==400;q.select.assert_not_called()

def test_filters_are_inclusive_wat_days_stable_order_and_campus_scoped():
 _,status,q=listing('from_date=2026-11-07&to_date=2026-11-07&status=success&campus_id='+B+'&offset=50')
 assert status==200;q.gte.assert_called_once_with('created_at','2026-11-06T23:00:00+00:00');q.lt.assert_called_once_with('created_at','2026-11-07T23:00:00+00:00')
 q.eq.assert_any_call('status','processed');q.offset.assert_called_once_with(50);q.order.assert_any_call('id',ascending=False)
 assert A in q.or_.call_args.args[0] and B not in q.or_.call_args.args[0]

def test_global_failure_redacts_all_sensitive_fields_for_campus_admin():
 row={'id':ID,'provider':'paystack','status':'failed','campus_id':None,'payload':{'email':'private'},'error':'private details','headers':{'secret':'private'},'metadata':{'email':'private'},'reference':'private','response_body':'private'}
 response,status,_=listing(rows=[row]);assert status==200
 result=response.json['webhook_events'][0];assert result['payload_redacted'] is True
 assert not any(key in result for key in ('payload','error','headers','metadata','reference','response_body'))
 response,status,_=listing(rows=[row],role='super_admin');assert status==200 and response.json['webhook_events'][0]['payload']==row['payload']

def retry(row=None,claim='claimed',failure=None,role='admin'):
 row=row or {'id':ID,'provider':'paystack','event_type':'charge.success','reference':'controlled','payload':{'data':{'reference':'controlled'}},'campus_id':A,'status':'failed'}
 db,q=database(row)
 with app.test_request_context(method='POST'),patch.object(admin,'get_db',return_value=db),patch.object(webhooks,'_claim_provider_event',return_value=claim) as acquire,patch.object(webhooks,'reprocess_stored_event',return_value=A,side_effect=failure) as process:
  g.user_role=role;g.campus_id=A
  response,status=admin.retry_webhook_event.__wrapped__(ID)
 return response,status,q,acquire,process

@pytest.mark.parametrize('claim,status',[('busy',409),('processed',200)])
def test_admin_provider_race_does_not_run_handler(claim,status):
 response,actual,q,acquire,process=retry(claim=claim);assert actual==status;acquire.assert_called_once();process.assert_not_called();q.update.assert_not_called()

def test_claim_precedes_replay_and_completion():
 response,status,q,acquire,process=retry();assert status==200 and response.json['status']=='processed'
 acquire.assert_called_once_with('paystack','charge.success','controlled',{'data':{'reference':'controlled'}});process.assert_called_once();assert q.update.call_args.args[0]['status']=='processed'

def test_failed_handler_remains_retryable():
 response,status,q,acquire,process=retry(failure=ValueError('controlled mismatch'));assert status==502 and q.update.call_args.args[0]['status']=='failed'

@pytest.mark.parametrize('status,expected',[('processed',200),('processing',409),('unknown',400)])
def test_nonfailed_receipt_is_not_reexecuted(status,expected):
 response,actual,q,acquire,process=retry(row={'campus_id':A,'payload':{},'status':status});assert actual==expected;acquire.assert_not_called();process.assert_not_called()
