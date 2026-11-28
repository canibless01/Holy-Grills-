"""Actual admin handlers on disposable local PostgreSQL authorization-state races.
Uses service-like local access; existing live RLS evidence is separate.
"""
import json,sys,uuid,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask,g
from app.routes import admin
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent';C,U,A=[str(uuid.uuid4()) for _ in range(3)];app=Flask(__name__);barrier=None;local=threading.local()
def sql(statement,args=()):
 c=psycopg2.connect(DSN);c.autocommit=True
 try:
  with c.cursor(cursor_factory=RealDictCursor) as q:
   q.execute("SET request.jwt.claims='{\"role\":\"service_role\"}'");q.execute(statement,args);rows=[dict(row) for row in q.fetchall()] if q.description else []
  return json.loads(json.dumps(rows,default=str))
 finally:c.close()
class DB:
 def table(self,name):return Query(name)
class Query:
 def __init__(self,table):self.table=table;self.filters=[]
 def select(self,*a):return self
 def eq(self,key,value):assert key in ('id','user_id','role','campus_id','is_active');self.filters.append((key,value));return self
 def is_(self,key,value):return self.eq(key,None if value=='null' else value)
 def single(self):return self
 def limit(self,*a):return self
 @property
 def not_(self):return self
 def in_(self,*a):return self
 def execute(self):
  if self.table=='orders':return []
  assert self.table=='profiles'
  rows=sql('SELECT * FROM profiles WHERE id=%s',(U,));row=rows[0] if rows else None
  if barrier and not getattr(local,'synced',False):local.synced=True;barrier.wait(timeout=10)
  return row
 def update(self,payload):
  assert self.table=='profiles';keys=list(payload);assert set(keys)<={'role','campus_id','is_active','deactivated_at','deactivated_by','deactivation_reason'}
  where=[];args=[]
  for k,v in self.filters:
   where.append(k+' IS NULL' if v is None else k+'=%s')
   if v is not None:args.append(v)
  return sql('UPDATE profiles SET '+','.join(k+'=%s' for k in keys)+' WHERE '+' AND '.join(where)+' RETURNING *',[payload[k] for k in keys]+args)
 def delete(self):assert self.table=='device_tokens';return []
def call(body,kind='role'):
 with app.test_request_context('/',method='POST',json=body):
  g.user_id=A;g.user_role='admin';g.campus_id=C
  response,status=(admin.change_user_role if kind=='role' else admin.deactivate_user).__wrapped__(U);return status,response.json
try:
 sql("INSERT INTO campuses(id,name,slug) VALUES(%s,'[LOCAL audit] Staff','audit-'||%s)",(C,C))
 sql("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,'{}'),(%s,%s,'{}')",(U,'audit-'+U+'@example.invalid',A,'audit-'+A+'@example.invalid'))
 sql("UPDATE profiles SET campus_id=%s,role='student',is_active=true WHERE id=%s",(C,U));sql("UPDATE profiles SET campus_id=%s,role='admin',is_active=true WHERE id=%s",(C,A))
 with patch.object(admin,'get_user_client',return_value=DB()),patch.object(admin,'get_db',return_value=DB()),patch.object(admin,'assert_can_modify'),patch.object(admin,'_audit',return_value=True) as audit,patch.object(admin,'send_notification') as notice,patch.object(admin,'_revoke_supabase_sessions',return_value=MagicMock(status_code=200)) as revoke:
  barrier=threading.Barrier(2)
  with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(lambda role:call({'role':role,'expected_role':'student','expected_campus_id':C,'expected_is_active':True}),('kitchen','rider')))
  barrier=None;assert sorted(status for status,_ in replies)==[200,409],replies;assert audit.call_count==1
  row=sql('SELECT * FROM profiles WHERE id=%s',(U,))[0]
  replay=call({'role':row['role'],'expected_role':'student','expected_campus_id':C,'expected_is_active':True});assert replay[0]==200 and audit.call_count==1
  with ThreadPoolExecutor(max_workers=8) as pool:replies=list(pool.map(lambda _:call({'expected_role':row['role'],'expected_campus_id':C,'expected_is_active':True},'deactivate'),range(8)))
  assert all(status in (200,409) for status,_ in replies),replies
  assert notice.call_count==revoke.call_count==1 and audit.call_count==2
  assert sql('SELECT is_active FROM profiles WHERE id=%s',(U,))[0]['is_active'] is False
  print(json.dumps({'competing_role_one_winner':True,'exact_role_retry_no_audit_repeat':True,'deactivation_sessions':8,'deactivation_notices':1,'revocation_calls':1,'no_real_provider_calls':True}))
finally:
 sql('DELETE FROM profiles WHERE id IN (%s,%s)',(U,A));sql('DELETE FROM auth.users WHERE id IN (%s,%s)',(U,A));sql('DELETE FROM campuses WHERE id=%s',(C,))
