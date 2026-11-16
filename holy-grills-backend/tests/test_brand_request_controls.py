"""Actual brand handlers and stored request/expected-status contracts."""
from copy import deepcopy
from unittest.mock import patch
import pytest
from flask import Flask
from app.routes import analytics as routes
from app.db import SupabaseError
app=Flask(__name__)
ID='11111111-1111-4111-8111-111111111111'
PAYLOAD={'request_id':ID,'brand_name':'  Campus partner  ','contact_email':'INFO@EXAMPLE.COM','requested_data':{'sales_summary':True}}
class DB:
 def __init__(self):self.rows={};self.race=None;self.fail=None;self.updates=0
 def table(self,name):assert name=='brand_partnership_requests';return Query(self)
class Query:
 def __init__(self,db):self.db=db;self.filters=[];self.pending=None
 def select(self,*a):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def is_(self,k,v):return self.eq(k,None if v=='null' else v)
 def single(self):return self
 def insert(self,payload):
  if self.db.fail:raise self.db.fail
  if payload['id'] in self.db.rows:raise SupabaseError('duplicate',409,{'code':'23505'})
  self.db.rows[payload['id']]={**deepcopy(payload),'shared_at':None};return [deepcopy(self.db.rows[payload['id']])]
 def update(self,payload):self.pending=payload;return self
 def execute(self):
  if self.pending is not None and self.db.race:self.db.race(self.db)
  rows=[r for r in self.db.rows.values() if all(r.get(k)==v for k,v in self.filters)]
  if self.pending is not None:
   for r in rows:r.update(self.pending);self.db.updates+=1
   return deepcopy(rows)
  return deepcopy(rows[0]) if rows else None

def call(db,payload,update=False):
 with app.test_request_context('/',method='PATCH' if update else 'POST',json=payload),patch.object(routes,'get_user_client',return_value=db):
  result,status=routes.update_brand_partnership.__wrapped__(ID) if update else routes.create_brand_partnership.__wrapped__()
  return result.json,status

def test_create_retry_keeps_original_row_and_later_status():
 db=DB();first,status=call(db,PAYLOAD);assert status==201 and first['contact_email']=='info@example.com'
 db.rows[ID]['status']='approved';saved,status=call(db,PAYLOAD);assert status==200 and saved['status']=='approved' and len(db.rows)==1
 assert saved['requested_data']=={'sales_summary':True}

@pytest.mark.parametrize('change',[{'brand_name':'Different'},{'contact_email':'new@example.com'},{'requested_data':{'different':True}}])
def test_reused_intent_cannot_replace_original_details(change):
 db=DB();call(db,PAYLOAD);_,status=call(db,{**PAYLOAD,**change});assert status==409 and len(db.rows)==1

@pytest.mark.parametrize('change',[{'request_id':'bad'},{'contact_email':'wrong'},{'brand_name':[]},{'requested_data':[]},{'requested_data':{'x':float('nan')}},{'requested_data':{'x':'x'*10001}}])
def test_bad_fields_do_not_insert(change):
 db=DB();_,status=call(db,{**PAYLOAD,**change});assert status==400 and not db.rows

def test_non_unique_database_error_is_not_relabelled_as_retry():
 db=DB();db.fail=SupabaseError('RLS denied',403,{'code':'42501'})
 with pytest.raises(SupabaseError):call(db,PAYLOAD)

def test_status_is_conditional_and_exact_retry_does_not_write_twice():
 db=DB();call(db,PAYLOAD);row,status=call(db,{'status':'approved','expected_status':'pending'},True);assert status==200 and row['status']=='approved' and db.updates==1
 _,status=call(db,{'status':'approved','expected_status':'pending'},True);assert status==200 and db.updates==1
 _,status=call(db,{'status':'rejected','expected_status':'pending'},True);assert status==409 and db.rows[ID]['status']=='approved'

def test_race_after_read_cannot_overwrite_newer_status():
 db=DB();call(db,PAYLOAD);db.race=lambda d:d.rows[ID].update(status='approved')
 _,status=call(db,{'status':'rejected','expected_status':'pending'},True);assert status==409 and db.updates==0 and db.rows[ID]['status']=='approved'

def test_unknown_row_and_bad_status_are_rejected():
 db=DB();_,status=call(db,{'status':'approved'},True);assert status==404
 call(db,PAYLOAD);_,status=call(db,{'status':'arbitrary'},True);assert status==400
