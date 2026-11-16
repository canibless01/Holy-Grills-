"""Catering editor contracts using actual handlers, no external notifications."""
from copy import deepcopy
import inspect
from unittest.mock import patch
import pytest
from flask import Flask,g
from app.routes import events
app=Flask(__name__);C='11111111-1111-4111-8111-111111111111';R='22222222-2222-4222-8222-222222222222';K='33333333-3333-4333-8333-333333333333';V='2026-11-15T10:00:00+00:00'
class DB:
 def __init__(self):self.row={'id':R,'campus_id':C,'status':'new','quoted_amount':None,'notes':'','assigned_to':None,'updated_at':V};self.staff={'id':K,'campus_id':C,'role':'kitchen','is_active':True};self.writes=[];self.race=None
 def table(self,name):return Query(self,name)
class Query:
 def __init__(self,db,table):self.db=db;self.table=table;self.filters=[]
 def select(self,*a):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def single(self):return self
 def execute(self):
  row=self.db.staff if self.table=='profiles' else self.db.row
  return deepcopy(row) if row and all(row.get(k)==v for k,v in self.filters) else None
 def update(self,payload):
  if self.db.race:self.db.race(self.db)
  if not all(self.db.row.get(k)==v for k,v in self.filters):return []
  self.db.row.update(payload);self.db.row['updated_at']='2026-11-15T11:00:00+00:00';self.db.writes.append(deepcopy(payload));return [deepcopy(self.db.row)]
def call(db,payload,role='admin',identifier=R):
 with app.test_request_context('/',method='PATCH',json=payload),patch.object(events,'get_user_client',return_value=db),patch.object(events,'get_db',return_value=db),patch.object(events,'assert_can_modify'):
  g.user_id=K;g.user_role=role;g.campus_id=C
  response,status=inspect.unwrap(events.update_catering_request)(identifier)
  return response.json,status

def test_zero_quote_and_selected_staff_persist_and_exact_lost_response_retry_replays():
 db=DB();payload={'status':'quoted','quoted_amount':0,'notes':'Internal only','assigned_to':K,'expected_updated_at':V}
 row,status=call(db,payload);assert status==200 and row['quoted_amount']==0 and row['assigned_to']==K
 row,status=call(db,payload);assert status==200 and len(db.writes)==1

@pytest.mark.parametrize('quote',[-1,True,float('nan'),float('inf'),1000000000000,'wrong'])
def test_bad_quotes_never_write(quote):
 db=DB();_,status=call(db,{'quoted_amount':quote});assert status==400 and not db.writes

def test_stale_edit_does_not_overwrite_and_select_update_race_is_guarded():
 db=DB();_,status=call(db,{'notes':'Older draft','expected_updated_at':'2026-11-15T09:00:00Z'});assert status==409 and not db.writes
 db.race=lambda d:d.row.update(notes='Winning edit',updated_at='2026-11-15T11:00:00+00:00')
 _,status=call(db,{'notes':'Lost edit','expected_updated_at':V});assert status==409 and db.row['notes']=='Winning edit' and not db.writes

@pytest.mark.parametrize('staff_change',[{'is_active':False},{'campus_id':R},{'role':'student'},{'role':'rider'}])
def test_ineligible_staff_cannot_be_assigned(staff_change):
 db=DB();db.staff.update(staff_change);_,status=call(db,{'assigned_to':K});assert status==400 and not db.writes

def test_kitchen_remains_assigned_only_and_cannot_quote_or_assign():
 db=DB();db.row.update(assigned_to=K,status='confirmed')
 _,status=call(db,{'quoted_amount':1},'kitchen');assert status==403
 _,status=call(db,{'status':'in_progress'},'kitchen');assert status==200
 db.row['assigned_to']=R;_,status=call(db,{'status':'completed'},'kitchen');assert status==404

def test_malformed_identifier_or_version_does_not_write():
 db=DB();_,status=call(db,{'notes':'x'},identifier='bad');assert status==404
 _,status=call(db,{'notes':'x','expected_updated_at':'bad'});assert status==400 and not db.writes

@pytest.mark.parametrize('role,scope',[('admin',C),('super_admin',C),('super_admin',None),('kitchen',C)])
def test_list_filters_pages_stably_and_binds_scope(role,scope):
 from unittest.mock import MagicMock
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','or_','order','limit','offset'):getattr(q,method).return_value=q
 q.execute.return_value=[]
 with app.test_request_context('/?limit=25&offset=50&status=quoted&q=Partner%2C%28%25%29'),patch.object(events,'get_db',return_value=db),patch.object(events,'get_user_client',return_value=db),patch.object(events,'resolve_scoped_campus_id',return_value=scope):
  g.user_id=K;g.user_role=role;g.campus_id=C
  _,status=inspect.unwrap(events.list_catering_requests)()
 assert status==200;q.limit.assert_called_once_with(25);q.offset.assert_called_once_with(50);q.order.assert_called_once_with('created_at.desc,id',ascending=False)
 expression=q.or_.call_args.args[0];assert expression.count(',')==2 and 'Partner' in expression and '%' not in expression and '(' not in expression
 if scope:q.eq.assert_any_call('campus_id',C)
 if role=='kitchen':q.eq.assert_any_call('assigned_to',K)
 q.eq.assert_any_call('status','quoted')

def test_bad_list_status_never_executes_the_query():
 from unittest.mock import MagicMock
 db=MagicMock();db.table.return_value.select.return_value.eq.return_value=db.table.return_value
 with app.test_request_context('/?status=wrong'),patch.object(events,'get_user_client',return_value=db),patch.object(events,'resolve_scoped_campus_id',return_value=None):
  g.user_role='super_admin';_,status=inspect.unwrap(events.list_catering_requests)()
 assert status==400;db.table.return_value.execute.assert_not_called()
