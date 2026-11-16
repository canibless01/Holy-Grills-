"""Role/access edits bind the displayed and selected authorization state."""
from copy import deepcopy
import inspect
from unittest.mock import patch,MagicMock
import pytest
from flask import Flask,g
from app.routes import admin
app=Flask(__name__);C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';A='33333333-3333-4333-8333-333333333333'
class DB:
 def __init__(self):self.row={'id':U,'role':'student','campus_id':C,'is_active':True,'full_name':'Fixture','email':'fixture@example.invalid'};self.writes=[];self.race=None
 def table(self,name):return Query(self,name)
class Query:
 def __init__(self,db,table):self.db=db;self.table=table;self.filters=[]
 def select(self,*a):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def is_(self,k,v):return self.eq(k,None if v=='null' else v)
 def single(self):return self
 def limit(self,*a):return self
 @property
 def not_(self):return self
 def in_(self,*a):return self
 def execute(self):
  if self.table=='orders':return []
  if self.table=='campuses':return {'id':C}
  return deepcopy(self.db.row) if self.db.row and all(self.db.row.get(k)==v for k,v in self.filters) else None
 def update(self,payload):
  if self.db.race:self.db.race(self.db)
  if not all(self.db.row.get(k)==v for k,v in self.filters):return []
  self.db.row.update(payload);self.db.writes.append(deepcopy(payload));return [deepcopy(self.db.row)]
 def delete(self):return []
def call(db,kind,body,actor='admin'):
 with app.test_request_context('/',method='POST',json=body),patch.object(admin,'get_user_client',return_value=db),patch.object(admin,'get_db',return_value=db),patch.object(admin,'assert_can_modify'),patch.object(admin,'_audit',return_value=True),patch.object(admin,'send_notification') as notice,patch.object(admin,'_revoke_supabase_sessions',return_value=MagicMock(status_code=200)) as revoke:
  g.user_id=A;g.user_role=actor;g.campus_id=C
  fn={'role':admin.change_user_role,'deactivate':admin.deactivate_user,'activate':admin.activate_user}[kind]
  response,status=inspect.unwrap(fn)(U)
  return response.json,status,notice.call_count,revoke.call_count

def expected(db):return {'expected_role':db.row['role'],'expected_campus_id':db.row['campus_id'],'expected_is_active':db.row['is_active']}
@pytest.mark.parametrize('kind',['role','deactivate','activate'])
def test_displayed_state_and_race_after_read_cannot_overwrite_new_role(kind):
 db=DB()
 if kind=='activate':db.row['is_active']=False
 body={**expected(db),**({'role':'rider'} if kind=='role' else {})}
 db.row['role']='kitchen';_,status,notice,revoke=call(db,kind,body);assert status==409 and not db.writes and notice==revoke==0
 db.row['role']='student';db.race=lambda d:d.row.update(role='super_admin',campus_id=None)
 _,status,notice,revoke=call(db,kind,body);assert status==409 and not db.writes and notice==revoke==0 and db.row['role']=='super_admin'

@pytest.mark.parametrize('kind',['role','deactivate','activate'])
def test_successful_edit_and_same_result_retry_do_not_repeat_side_effects(kind):
 db=DB()
 if kind=='activate':db.row['is_active']=False
 body={**expected(db),**({'role':'rider'} if kind=='role' else {})}
 _,status,_,_=call(db,kind,body);assert status==200 and len(db.writes)==1
 _,status,notice,revoke=call(db,kind,body);assert status==200 and len(db.writes)==1 and notice==revoke==0

@pytest.mark.parametrize('bad',[{'expected_role':[]},{'expected_role':'bad'},{'expected_is_active':'true'},{'expected_campus_id':'wrong'}])
def test_bad_expected_values_do_not_write(bad):
 db=DB();_,status,_,_=call(db,'role',{'role':'rider',**bad});assert status==400 and not db.writes

def test_global_super_admin_demotion_binds_null_campus_and_requires_target_campus():
 db=DB();db.row.update(role='super_admin',campus_id=None)
 body={'role':'student',**expected(db)};_,status,_,_=call(db,'role',body,'super_admin');assert status==400
 body['campus_id']=C;_,status,_,_=call(db,'role',body,'super_admin');assert status==200 and db.row['campus_id']==C and db.row['role']=='student'

def test_campus_admin_retains_manager_activation_authority_but_not_admin_account_control():
 db=DB();db.row.update(role='community_manager',is_active=False)
 _,status,_,_=call(db,'activate',expected(db));assert status==200
 db.row['role']='admin';_,status,_,_=call(db,'deactivate',expected(db));assert status==403
