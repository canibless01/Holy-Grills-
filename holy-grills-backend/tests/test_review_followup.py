"""Follow-up flags cannot edit customer scores, awards or another campus."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from werkzeug.exceptions import Forbidden
from app.routes import admin
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';R='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
BASE={'id':R,'campus_id':A,'is_flagged':False,'updated_at':'2026-11-05T10:00:00+00:00','rating':4,'hp_awarded':20}
BODY={'is_flagged':True,'expected_flagged':False,'expected_updated_at':BASE['updated_at']}
def invoke(body=None,row=None,result=None,role='admin'):
 db=MagicMock();q=db.table.return_value
 for key in ('eq','is_'):getattr(q,key).return_value=q
 q.update.return_value=[{**BASE,'is_flagged':True}] if result is None else result
 with app.test_request_context(method='PATCH',json=BODY if body is None else body),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'fetch_or_403',return_value=(BASE if row is None else row,None)),patch.object(admin,'_audit') as audit:
  g.user_id=R;g.user_role=role;g.campus_id=A
  response,status=admin.flag_review.__wrapped__(R)
 return response,status,q,audit

def test_flag_only_changes_followup_metadata_and_logs_correct_campus():
 response,status,q,audit=invoke();assert status==200 and response.json['rating']==4 and response.json['hp_awarded']==20
 patch_data=q.update.call_args.args[0];assert set(patch_data)=={'is_flagged','updated_at'}
 assert q.eq.call_args_list[-1].args==('updated_at',BASE['updated_at']);audit.assert_called_once();assert audit.call_args.kwargs['target_campus_id']==A

def test_matching_response_loss_replay_does_not_update_or_log_again():
 _,status,q,audit=invoke(row={**BASE,'is_flagged':True});assert status==200;q.update.assert_not_called();audit.assert_not_called()

def test_stale_conditional_write_is_conflict_not_success():
 _,status,_,audit=invoke(result=[]);assert status==409;audit.assert_not_called()

def test_foreign_campus_denied_and_super_admin_allowed():
 with pytest.raises(Forbidden):invoke(row={**BASE,'campus_id':B})
 _,status,_,_=invoke(row={**BASE,'campus_id':B},role='super_admin');assert status==200

@pytest.mark.parametrize('body',[[1],{**BODY,'is_flagged':'false'},{**BODY,'expected_flagged':0},{**BODY,'expected_updated_at':'bad'},{**BODY,'rating':5},{**BODY,'hp_awarded':9999},{}])
def test_invalid_or_protected_fields_refused(body):
 _,status,q,_=invoke(body=body);assert status==400;q.update.assert_not_called()
