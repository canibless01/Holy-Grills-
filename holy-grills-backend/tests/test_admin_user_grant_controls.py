"""Admin identities, scopes, recipients and retry keys; no live grants/providers."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import hp,admin
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333';ACTOR='44444444-4444-4444-8444-444444444444';KEY='55555555-5555-4555-8555-555555555555'
app=Flask(__name__)
BODY={'user_id':U,'amount':50,'notes':'Launch adjustment','grant_id':KEY}
def invoke(body=None,target=None,previous=None,role='admin',error=None):
 db=MagicMock();profile=MagicMock();ledger=MagicMock()
 db.table.side_effect=lambda name:profile if name=='profiles' else ledger
 for q in (profile,ledger):
  for name in ('select','eq','single'):getattr(q,name).return_value=q
 profile.execute.return_value={'campus_id':A,'is_active':True} if target is None else target
 saved={'id':KEY,'amount':50,'type':'earn','metadata':{'notes':'Launch adjustment'},'issued_by_admin_id':ACTOR,'balance_after':50}
 ledger.execute.side_effect=[previous,saved] if previous is None else [previous]
 with app.test_request_context(method='POST',json=BODY if body is None else body),patch.object(hp,'get_user_client',return_value=db),patch.object(hp,'award_active_hp',return_value={'awarded':50,'replayed':False},side_effect=error) as award,patch.object(hp,'_log_admin_action') as audit:
  g.user_id=ACTOR;g.user_role=role;g.campus_id=A
  response,status=hp.admin_grant.__wrapped__()
 return response,status,award,audit,ledger

def test_single_grant_has_actor_bound_reference_disables_multiplier_and_logs_once():
 response,status,award,audit,_=invoke();assert status==200 and response.json['new_balance']==50 and response.json['amount']==50
 kw=award.call_args.kwargs
 assert kw['reference_id'] and kw['reference_type']=='admin_grant' and kw['source_type']=='admin_grant'
 assert kw['issued_by_admin_id']==ACTOR and kw['campus_id']==A and kw['apply_multiplier'] is False
 audit.assert_called_once()
 assert invoke()[2].call_args.kwargs['reference_id']==kw['reference_id']

def test_matching_receipt_replay_does_not_credit_counters_or_audit_again():
 saved={'amount':50,'type':'earn','metadata':{'notes':'Launch adjustment'},'issued_by_admin_id':ACTOR,'balance_after':50}
 response,status,award,audit,_=invoke(previous=saved)
 assert status==200 and response.json['replayed'] and response.json['awarded']==0;award.assert_not_called();audit.assert_not_called()

@pytest.mark.parametrize('changed',[{'amount':51},{'metadata':{'notes':'different'}},{'issued_by_admin_id':U}])
def test_changed_receipt_refused_without_another_credit(changed):
 saved={'amount':50,'type':'earn','metadata':{'notes':'Launch adjustment'},'issued_by_admin_id':ACTOR,**changed}
 _,status,award,_,_=invoke(previous=saved);assert status==409;award.assert_not_called()

@pytest.mark.parametrize('fields',[{'grant_id':None},{'user_id':'bad'},{'amount':True},{'amount':1.5},{'amount':float('inf')},{'amount':0},{'amount':100001},{'notes':''},{'notes':'x'*201}])
def test_bad_grant_inputs_do_not_award(fields):
 _,status,award,_,_=invoke(body={**BODY,**fields});assert status==400;award.assert_not_called()

def test_self_inactive_and_foreign_grants_are_denied():
 assert invoke(body={**BODY,'user_id':ACTOR})[1]==403
 assert invoke(target={'campus_id':A,'is_active':False})[1]==400
 with pytest.raises(Forbidden):invoke(target={'campus_id':B,'is_active':True})
 assert invoke(target={'campus_id':B,'is_active':True},role='super_admin')[1]==200

@pytest.mark.parametrize('dry,status',[(True,200),(False,400)])
def test_explicit_empty_bulk_list_never_becomes_a_global_segment(dry,status):
 db=MagicMock()
 with app.test_request_context(method='POST',json={'amount':50,'reason':'Audit','user_ids':[],'dry_run':dry}),patch.object(admin,'get_user_client',return_value=db):
  g.user_id=ACTOR;g.user_role='super_admin';g.campus_id=A
  response,actual=admin.bulk_grant_hp.__wrapped__()
 assert actual==status;db.rpc.assert_not_called();db.table.assert_not_called()
 if dry:assert response.json['matched_count']==0

@pytest.mark.parametrize('fields',[{'user_ids':None},{'amount':1.5},{'amount':float('inf')},{'amount':True}])
def test_invalid_bulk_inputs_are_rejected_before_any_recipient_read(fields):
 with app.test_request_context(method='POST',json={'amount':50,'reason':'Audit',**fields}),patch.object(admin,'get_user_client') as db:
  _,status=admin.bulk_grant_hp.__wrapped__()
 assert status==400;db.assert_not_called()
