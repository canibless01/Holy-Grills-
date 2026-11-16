"""Manual expiry is scoped, previewed and identified; jobs retain their own path."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import hp
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333';ACTOR='44444444-4444-4444-8444-444444444444';KEY='55555555-5555-4555-8555-555555555555'
app=Flask(__name__)
BODY={'user_id':U,'amount':None,'expected_balance':100,'notes':'Confirmed reason','request_id':KEY}
def invoke(body=None,campus=A,role='admin',result=None):
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','single'):getattr(q,name).return_value=q
 q.execute.return_value={'campus_id':campus}
 db.rpc.return_value={'success':True,'expired':100,'new_balance':0,'replayed':False} if result is None else result
 with app.test_request_context(method='POST',json=BODY if body is None else body),patch.object(hp,'get_user_client',return_value=db),patch.object(hp,'get_db',return_value=db),patch('app.services.hp_service.recalculate_tier') as tier,patch.object(hp,'_log_admin_action') as audit:
  g.user_id=ACTOR;g.user_role=role;g.campus_id=A
  response,status=hp.admin_expire.__wrapped__()
 return response,status,db,tier,audit

def test_blank_all_mode_has_expected_balance_and_actor_bound_identity():
 response,status,db,tier,audit=invoke();assert status==200 and response.json['expired']==100
 params=db.rpc.call_args.args[1];assert db.rpc.call_args.args[0]=='hg_admin_expire_hp'
 assert params['p_actor_id']==ACTOR and params['p_user_id']==U and params['p_amount'] is None and params['p_expected_balance']==100
 assert params['p_request_id']==invoke()[2].rpc.call_args.args[1]['p_request_id']
 tier.assert_called_once_with(U,campus_id=A);audit.assert_called_once()

def test_receipt_replay_does_not_log_a_second_admin_action():
 _,status,_,tier,audit=invoke(result={'success':True,'replayed':True,'expired':100,'new_balance':20})
 assert status==200;tier.assert_called_once();audit.assert_not_called()

def test_foreign_campus_denied_but_super_admin_can_expire():
 with pytest.raises(Forbidden):invoke(campus=B)
 assert invoke(campus=B,role='super_admin')[1]==200

@pytest.mark.parametrize('fields',[{'request_id':None},{'user_id':'bad'},{'expected_balance':None},{'expected_balance':-1},{'amount':0},{'amount':1.5},{'amount':True},{'amount':float('inf')},{'notes':''}])
def test_invalid_preview_or_amount_never_calls_rpc(fields):
 _,status,db,_,_=invoke(body={**BODY,**fields});assert status==400;db.rpc.assert_not_called()

@pytest.mark.parametrize('code,status',[('expiry_forbidden',403),('expiry_target_missing',404),('expiry_conflict',409),('expiry_balance_changed',409),('expiry_insufficient',409),('nothing_to_expire',409),('invalid_expiry',400),('unknown',503)])
def test_expected_database_outcomes_have_clean_status_and_no_audit(code,status):
 response,actual,_,tier,audit=invoke(result={'error':code});assert actual==status and response.json['error'];tier.assert_not_called();audit.assert_not_called()
