"""Actual prize-pool handlers: UUID create replay, snapshot writes and retained scope."""
from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from werkzeug.exceptions import Forbidden
from app.db import SupabaseError
from app.routes import admin
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';P='33333333-3333-4333-8333-333333333333';STAMP='2026-11-15T10:00:00+00:00'
BODY={'name':'Fixture','weight':10,'is_active':True,'campus_id':A,'reward_config':{'kind':'hp','amount':40},'request_id':P}
ROW={**{k:v for k,v in BODY.items() if k!='request_id'},'id':P,'updated_at':STAMP}
def database():
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','is_','single','insert','update'):getattr(q,name).return_value=q
 return db,q

def invoke(handler,body,db,role='admin',campus=A,args=()):
 with Flask(__name__).test_request_context(json=body),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'get_db',return_value=db):
  g.user_role=role;g.campus_id=campus;g.user_id='actor'
  return handler.__wrapped__(*args)
@pytest.mark.parametrize('role,requested,stored',[('admin',A,A),('super_admin',A,A),('super_admin',None,None)])
def test_create_uses_intent_id_and_role_scope(role,requested,stored):
 db,q=database();q.execute.side_effect=([{'id':A}], [dict(ROW,campus_id=stored)]) if stored else [[dict(ROW,campus_id=stored)]]
 _,status=invoke(admin.create_spin_pool_prize,{**BODY,'campus_id':requested},db,role=role)
 assert status==201;payload=q.insert.call_args.args[0];assert payload['id']==P and payload['campus_id']==stored
@pytest.mark.parametrize('matching',[True,False])
def test_duplicate_create_returns_only_same_original_payload(matching):
 db,q=database();q.insert.side_effect=SupabaseError('duplicate',409,{'code':'23505'});q.execute.side_effect=[[{'id':A}],dict(ROW,name='Fixture' if matching else 'Edited elsewhere')]
 response,status=invoke(admin.create_spin_pool_prize,BODY,db)
 assert status==(200 if matching else 409)
 if matching:assert response.json['id']==P
 q.update.assert_not_called()
@pytest.mark.parametrize('invalid',[True,'bad',[],123])
def test_invalid_create_intent_never_inserts(invalid):
 db,q=database();_,status=invoke(admin.create_spin_pool_prize,{**BODY,'request_id':invalid},db)
 assert status==400;q.insert.assert_not_called()
def test_foreign_create_is_denied():
 db,q=database();_,status=invoke(admin.create_spin_pool_prize,{**BODY,'campus_id':B},db)
 assert status==403;q.insert.assert_not_called()
@pytest.mark.parametrize('same',[False,True])
def test_stale_edit_rejects_change_but_recovers_identical_result(same):
 db,q=database();q.execute.return_value=ROW
 response,status=invoke(admin.update_spin_pool_prize,{'name':'Fixture' if same else 'New name','expected_updated_at':'2026-11-15T09:00:00+00:00'},db,args=(P,))
 assert status==(200 if same else 409);q.update.assert_not_called()
def test_update_conditions_write_on_selected_version():
 db,q=database();q.execute.side_effect=[ROW,[dict(ROW,name='New name')]]
 _,status=invoke(admin.update_spin_pool_prize,{'name':'New name','expected_updated_at':STAMP},db,args=(P,))
 assert status==200;q.eq.assert_any_call('updated_at',STAMP)
@pytest.mark.parametrize('matching',[True,False])
def test_lost_update_race_recovers_only_an_identical_committed_edit(matching):
 db,q=database();q.execute.side_effect=[ROW,[],dict(ROW,name='New name' if matching else 'Different name')]
 _,status=invoke(admin.update_spin_pool_prize,{'name':'New name','expected_updated_at':STAMP},db,args=(P,))
 assert status==(200 if matching else 409);q.update.assert_called_once()
def test_foreign_edit_is_denied():
 db,q=database();q.execute.return_value=dict(ROW,campus_id=B)
 with pytest.raises(Forbidden):invoke(admin.update_spin_pool_prize,{'name':'New name'},db,args=(P,))
 q.update.assert_not_called()
