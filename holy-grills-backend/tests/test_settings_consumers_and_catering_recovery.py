"""Configured transfer limits and saved catering email survive missing responses/processes."""
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import hp,events
from app.services import operations_email
from app.utils.settings import MalformedSettingError,DatabaseUnavailableError
from app.db import TableQuery

APP=Flask(__name__)

def query_db(value):
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','is_','single'):getattr(q,name).return_value=q
 q.execute.return_value={'value':value}
 return db,q

@pytest.mark.parametrize('value',[0,10,'25',{'value':50}])
def test_transfer_setting_uses_campus_value_and_preserves_zero(value):
 db,q=query_db(value)
 with APP.test_request_context():
  g.campus_id='campus'
  assert hp._transfer_setting(db,'hp_transfer_min_orders','HP_TRANSFER_MIN_ORDERS',3)==int(value.get('value') if isinstance(value,dict) else value)
 q.eq.assert_any_call('campus_id','campus')

@pytest.mark.parametrize('value',[True,-1,'NaN','Infinity',1.5,'1.5',{},2147483648])
def test_malformed_transfer_setting_does_not_authorize_a_transfer(value):
 db,_=query_db(value)
 with APP.test_request_context(),pytest.raises(MalformedSettingError):
  hp._transfer_setting(db,'hp_transfer_min_amount','HP_TRANSFER_MIN_AMOUNT',10)


def test_configured_minimum_stops_before_balance_or_money_rpc():
 db,_=query_db(50)
 with APP.test_request_context(method='POST',json={'recipient_id':'22222222-2222-4222-8222-222222222222','amount':20}),patch.object(hp,'get_user_client',return_value=db),patch.object(hp,'get_db',return_value=db),patch('app.services.feature_flags.is_feature_enabled',return_value=True),patch.object(hp,'get_hp_balance') as balance:
  g.user_id='owner';g.campus_id='campus'
  _,status=hp.transfer_hp.__wrapped__()
 assert status==400;balance.assert_not_called();db.rpc.assert_not_called()


def test_catering_protocol_is_explicit_and_does_not_modify_default_headers():
 client=SimpleNamespace(_service_headers=lambda:{'Authorization':'local-test'})
 q=TableQuery(client,'catering_requests')
 assert 'X-HG-Write-Protocol' not in q._headers()
 q._write_protocol='catering-status-v1'
 assert q._headers()['X-HG-Write-Protocol']=='catering-status-v1'
 assert 'X-HG-Write-Protocol' not in TableQuery(client,'orders')._headers()


def test_catering_render_uses_current_public_quote_without_private_notes():
 db,q=query_db(None);q.execute.side_effect=[{'name':'Campus'},{'campus_id':'campus','email':'Guest@Example.invalid','organizer_name':'<img src=x>','status':'quoted','quoted_amount':0,'notes':'Private admin note'}]
 row={'kind':'catering_status','campus_id':'campus','recipient':'guest@example.invalid','payload':{'request_id':'request','status':'quoted'}}
 subject,html=operations_email.render(db,row)
 assert 'Quoted' in subject and '0' in html
 assert '<img src=x>' not in html and 'Private admin note' not in html


def test_changed_catering_contact_stops_before_provider():
 db,q=query_db(None);q.execute.side_effect=[{'name':'Campus'},{'campus_id':'campus','email':'new@example.invalid','status':'confirmed'}]
 row={'kind':'catering_status','campus_id':'campus','recipient':'old@example.invalid','payload':{'request_id':'request','status':'confirmed'}}
 assert operations_email.render(db,row) is None


def test_catering_wake_claim_cannot_send_other_operator_emails():
 db=MagicMock();db.rpc.return_value=[]
 assert operations_email.dispatch_pending(db,catering_request_id='request')['accepted']==0
 db.rpc.assert_called_once_with('hg_operations_email_outbox',{'p_action':'claim','p_data':{'catering_request_id':'request'}})


def test_interrupted_render_does_not_advance_email_to_sending():
 db=MagicMock();db.rpc.return_value=[{'id':'mail','token':'lease','recipient':'guest@example.invalid'}]
 with patch.object(operations_email,'render',side_effect=RuntimeError('worker interrupted')),patch.object(operations_email,'send_email_routed') as transport:
  operations_email.dispatch_pending(db)
 assert db.rpc.call_count==1;transport.assert_not_called()


def test_transfer_rules_read_private_settings_server_side_not_through_student_rls():
    user_db,user_query=query_db(None);user_query.execute.return_value=[]
    service_db,service_query=query_db(0)
    with APP.test_request_context(),patch.object(hp,'get_db',return_value=service_db):
        g.campus_id='campus'
        assert hp._transfer_order_eligibility(user_db,'student')==(0,0)
    service_query.eq.assert_any_call('key','hp_transfer_min_orders')
    user_db.table.assert_called_once_with('orders')
