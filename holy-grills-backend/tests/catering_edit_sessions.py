"""Actual catering handler version/replay races on disposable local PostgreSQL.
Uses service-like local access; does not claim new live role/provider tests.
"""
import json,sys,uuid,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask,g
from app.routes import events
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent';C,R,U=[str(uuid.uuid4()) for _ in range(3)];barrier=None;local=threading.local();app=Flask(__name__)
def sql(query,args=()):
 c=psycopg2.connect(DSN);c.autocommit=True
 try:
  with c.cursor(cursor_factory=RealDictCursor) as q:q.execute(query,args);rows=[dict(r) for r in q.fetchall()] if q.description else []
  return json.loads(json.dumps(rows,default=str))
 finally:c.close()
class DB:
 def table(self,name):assert name=='catering_requests';return Query()
class Query:
 def __init__(self):self.filters=[]
 def select(self,*a):return self
 def eq(self,key,value):assert key in ('id','status','updated_at');self.filters.append((key,value));return self
 def single(self):return self
 def execute(self):
  result=sql('SELECT * FROM catering_requests WHERE '+' AND '.join(k+'=%s' for k,_ in self.filters),[v for _,v in self.filters]);row=result[0] if result else None
  if barrier and not getattr(local,'synced',False):local.synced=True;barrier.wait(timeout=10)
  return row
 def update(self,payload):
  keys=list(payload);assert set(keys)<= {'notes','quoted_amount'}
  return sql('UPDATE catering_requests SET '+','.join(k+'=%s' for k in keys)+' WHERE '+' AND '.join(k+'=%s' for k,_ in self.filters)+' RETURNING *',[payload[k] for k in keys]+[v for _,v in self.filters])
def call(payload):
 with app.test_request_context('/',method='PATCH',json=payload):
  g.user_role='admin';g.user_id=U;g.campus_id=C
  response,status=events.update_catering_request.__wrapped__(R);return status,response.json
try:
 sql("INSERT INTO campuses(id,name,slug) VALUES(%s,'[LOCAL audit] Catering','audit-'||%s)",(C,C))
 row=sql("INSERT INTO catering_requests(id,campus_id,organizer_name,email,phone,event_name,event_date,expected_guests) VALUES(%s,%s,'[LOCAL audit] Organizer','audit@example.invalid','08012345678','[LOCAL audit] Event','2026-12-01',10) RETURNING *",(R,C))[0]
 with patch.object(events,'get_user_client',return_value=DB()),patch.object(events,'assert_can_modify'):
  payload={'notes':'Same saved edit','quoted_amount':0,'expected_updated_at':row['updated_at']}
  with ThreadPoolExecutor(max_workers=8) as pool:replies=list(pool.map(lambda _:call(payload),range(8)))
  assert all(status==200 for status,_ in replies),replies
  saved=sql('SELECT * FROM catering_requests WHERE id=%s',(R,))[0];assert saved['notes']=='Same saved edit' and float(saved['quoted_amount'])==0
  barrier=threading.Barrier(2)
  with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(lambda note:call({'notes':note,'expected_updated_at':saved['updated_at']}),('Competing edit A','Competing edit B')))
  barrier=None;assert sorted(status for status,_ in replies)==[200,409],replies
  current=sql('SELECT * FROM catering_requests WHERE id=%s',(R,))[0];assert current['notes'] in ('Competing edit A','Competing edit B')
  print(json.dumps({'same_edit_handler_sessions':8,'all_replayed_safely':True,'zero_quote_preserved':True,'competing_edit_one_winner':True,'no_external_notification':True}))
finally:
 sql('DELETE FROM catering_requests WHERE id=%s',(R,));sql('DELETE FROM campuses WHERE id=%s',(C,))
