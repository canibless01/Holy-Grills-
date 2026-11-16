"""Independent actual-handler sessions against disposable local PostgreSQL only."""
import json,threading,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor,Json
from flask import Flask,g
from app.routes import admin as routes
from app.db import SupabaseError
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent';ID=str(uuid.uuid4());barrier=None;thread=threading.local()
class DB:
 def table(self,name):assert name=='exclusive_spin_prizes';return Query()
class Query:
 def __init__(self):self.filters=[];self.values=None;self.operation='select'
 def select(self,*a):return self
 def single(self):return self
 def eq(self,key,value):assert key in ('id','updated_at');self.filters.append((key,value));return self
 def is_(self,key,value):return self.eq(key,None if value=='null' else value)
 def insert(self,data):self.values=data;self.operation='insert';return self
 def update(self,data):self.values=data;self.operation='update';return self
 def execute(self):
  allowed={'id','name','weight','is_active','campus_id','reward_config','updated_at'}
  if self.values is not None:assert set(self.values)<=allowed
  keys=list(self.values or {});values=[Json(self.values[k]) if isinstance(self.values[k],dict) else self.values[k] for k in keys]
  if self.operation=='insert':return self.sql('INSERT INTO exclusive_spin_prizes('+','.join(keys)+') VALUES('+','.join(['%s']*len(keys))+') RETURNING *',values)
  args=[];where=[]
  for key,value in self.filters:
   where.append(key+' IS NULL' if value is None else key+'=%s')
   if value is not None:args.append(value)
  assert where
  if self.operation=='update':return self.sql('UPDATE exclusive_spin_prizes SET '+','.join(k+'=%s' for k in keys)+' WHERE '+' AND '.join(where)+' RETURNING *',values+args)
  rows=self.sql('SELECT * FROM exclusive_spin_prizes WHERE '+' AND '.join(where),args)
  if barrier and not getattr(thread,'read_seen',False):thread.read_seen=True;barrier.wait(timeout=10)
  return rows[0] if rows else None
 def sql(self,statement,args):
  c=psycopg2.connect(DSN);c.autocommit=True
  try:
   with c.cursor(cursor_factory=RealDictCursor) as q:
    q.execute("select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
    q.execute(statement,args);rows=[dict(r) for r in q.fetchall()]
   return json.loads(json.dumps(rows,default=lambda v:v.isoformat() if hasattr(v,'isoformat') else str(v)))
  except psycopg2.Error as e:raise SupabaseError(e.diag.message_primary,409 if e.pgcode=='23505' else 500,{'code':e.pgcode}) from e
  finally:c.close()
app=Flask(__name__);payload={'name':'[LOCAL audit] Spin','weight':10,'reward_config':{'kind':'hp','amount':40},'request_id':ID,'campus_id':None}
def call(body,update=False):
 with app.test_request_context(json=body):
  g.user_role='super_admin';g.campus_id=None;g.user_id='fixture'
  response,status=routes.update_spin_pool_prize.__wrapped__(ID) if update else routes.create_spin_pool_prize.__wrapped__()
  return status,response.json
try:
 with patch.object(routes,'get_user_client',return_value=DB()),patch.object(routes,'get_db',return_value=DB()):
  with ThreadPoolExecutor(max_workers=8) as pool:created=list(pool.map(lambda _:call(payload),range(8)))
  assert [s for s,_ in created].count(201)==1 and [s for s,_ in created].count(200)==7,created
  stamp=created[0][1]['updated_at'];assert call({**payload,'name':'Conflicting name'})[0]==409
  barrier=threading.Barrier(2)
  with ThreadPoolExecutor(max_workers=2) as pool:updated=list(pool.map(lambda name:call({'name':name,'expected_updated_at':stamp},True),('Competing A','Competing B')))
  barrier=None;assert sorted(s for s,_ in updated)==[200,409],updated
  winner=next(row['name'] for status,row in updated if status==200)
  assert call({'name':winner,'expected_updated_at':stamp},True)[0]==200
  assert call(payload)[0]==409 # Never overwrite a later edit on a create retry.
  with psycopg2.connect(DSN) as c:
   with c.cursor() as q:q.execute('select count(*) from exclusive_spin_prizes where id=%s',(ID,));assert q.fetchone()[0]==1
  print(json.dumps({'independent_create_sessions':8,'stored_rows':1,'competing_edit_one_winner':True,'identical_edit_retry':True,'later_edit_preserved':True,'live_database_touched':False}))
finally:
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:q.execute('delete from exclusive_spin_prizes where id=%s',(ID,))
