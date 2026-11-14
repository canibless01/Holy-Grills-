"""Real handler persistence races on disposable local PostgreSQL; no external APIs.
The adapter executes the route's PK and conditional-update contract using the
existing local table. It does not claim customer RLS/provider verification.
"""
import json,threading,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from flask import Flask
from app.routes import analytics as routes
from app.db import SupabaseError
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent'
ID=str(uuid.uuid4());barrier=None
class DB:
 def table(self,name):assert name=='brand_partnership_requests';return Query()
class Query:
 def __init__(self):self.filters=[];self.values=None
 def select(self,*a):return self
 def single(self):return self
 def eq(self,key,value):assert key in ('id','status','shared_at');self.filters.append((key,value));return self
 def is_(self,key,value):return self.eq(key,None if value=='null' else value)
 def insert(self,data):
  keys=list(data);assert set(keys)<= {'id','brand_name','contact_email','requested_data','status'}
  return self.sql('INSERT INTO brand_partnership_requests('+','.join(keys)+') VALUES('+','.join(['%s']*len(keys))+') RETURNING *',[Json(data[k]) if isinstance(data[k],dict) else data[k] for k in keys])
 def update(self,data):self.values=data;return self
 def execute(self):
  args=[];where=[]
  for key,value in self.filters:
   where.append(key+' IS NULL' if value is None else key+'=%s')
   if value is not None:args.append(value)
  if self.values is None:
   rows=self.sql('SELECT * FROM brand_partnership_requests WHERE '+' AND '.join(where),args)
   if barrier:barrier.wait(timeout=10)
   return rows[0] if rows else None
  keys=list(self.values);assert set(keys)<={'status','shared_at'}
  return self.sql('UPDATE brand_partnership_requests SET '+','.join(k+'=%s' for k in keys)+' WHERE '+' AND '.join(where)+' RETURNING *',[self.values[k] for k in keys]+args)
 def sql(self,statement,args):
  c=psycopg2.connect(DSN);c.autocommit=True
  try:
   with c.cursor(cursor_factory=RealDictCursor) as q:q.execute(statement,args);rows=[dict(row) for row in q.fetchall()]
   return [json.loads(json.dumps(row,default=str)) for row in rows]
  except psycopg2.Error as e:raise SupabaseError(e.diag.message_primary,409 if e.pgcode=='23505' else 500,{'code':e.pgcode}) from e
  finally:c.close()
app=Flask(__name__)
payload={'request_id':ID,'brand_name':'[LOCAL audit] Partner','contact_email':'audit@example.invalid','requested_data':{'sales_summary':True}}
def call(body,update=False):
 with app.test_request_context('/',method='PATCH' if update else 'POST',json=body):
  response,status=routes.update_brand_partnership.__wrapped__(ID) if update else routes.create_brand_partnership.__wrapped__()
  return status,response.json
try:
 with patch.object(routes,'get_user_client',return_value=DB()):
  with ThreadPoolExecutor(max_workers=8) as pool:created=list(pool.map(lambda _:call(payload),range(8)))
  assert [s for s,_ in created].count(201)==1 and [s for s,_ in created].count(200)==7,created
  assert call({**payload,'brand_name':'Changed'})[0]==409
  barrier=threading.Barrier(2)
  with ThreadPoolExecutor(max_workers=2) as pool:updated=list(pool.map(lambda s:call({'status':s,'expected_status':'pending'},True),('approved','rejected')))
  barrier=None;assert sorted(s for s,_ in updated)==[200,409],updated
  replay=call(payload);assert replay[0]==200 and replay[1]['status'] in ('approved','rejected')
  with psycopg2.connect(DSN) as c:
   with c.cursor() as q:q.execute('select count(*) from brand_partnership_requests where id=%s',(ID,));assert q.fetchone()[0]==1
  print(json.dumps({'handler_create_sessions':8,'rows':1,'same_intent_replay':True,'changed_intent_conflict':True,'competing_status_one_winner':True,'later_status_preserved_on_create_retry':True}))
finally:
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:q.execute('delete from brand_partnership_requests where id=%s',(ID,))
