"""Real automatic-preparation producer/status/DB loop, isolated rollback PG only.
No provider messages: the asynchronous sender is held; state triggers run normally.
"""
import json, re, sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from datetime import datetime, timedelta, time
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from flask import Flask
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services import automatic_preparation as auto, order_service as orders, feature_flags
from app.utils.tz import today_wat
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent'
c=psycopg2.connect(DSN);cursor=c.cursor(cursor_factory=RealDictCursor)
def run(query,args=()):
 cursor.execute(query,args)
 return json.loads(json.dumps([dict(row) for row in cursor.fetchall()],default=str)) if cursor.description else []
class Result(list):
 def execute(self):return self
class Query:
 def __init__(self,table):self.table=table;self.filters=[];self.args=[];self.sort=[];self.maximum=None;self.one=False
 def select(self,*_):return self
 def eq(self,k,v):self.filters.append(sql.SQL('{}=%s').format(sql.Identifier(k)));self.args.append(v);return self
 def in_(self,k,values):self.filters.append(sql.SQL('{}::text=ANY(%s)').format(sql.Identifier(k)));self.args.append(list(values));return self
 def is_(self,k,v):assert v=='null';self.filters.append(sql.SQL('{} IS NULL').format(sql.Identifier(k)));return self
 def or_(self,expression):
  def parts(text):
   depth=0;start=0;out=[]
   for index,char in enumerate(text):
    depth+=(char=='(')-(char==')')
    if char==',' and depth==0:out.append(text[start:index]);start=index+1
   return out+[text[start:]]
  def parse(term):
   for group,join in [('and',' AND '),('or',' OR ')]:
    if term.startswith(group+'('):return sql.SQL('(')+sql.SQL(join).join(parse(value) for value in parts(term[len(group)+1:-1]))+sql.SQL(')')
   field,operator,value=term.split('.',2);assert re.fullmatch('[a-z_]+',field)
   if operator=='is':assert value=='null';return sql.SQL('{} IS NULL').format(sql.Identifier(field))
   assert operator in ('eq','gte','lt')
   self.args.append(True if value=='true' else False if value=='false' else value)
   return sql.SQL('{} '+{'eq':'=','gte':'>=','lt':'<'}[operator]+' %s').format(sql.Identifier(field))
  self.filters.append(sql.SQL('(')+sql.SQL(' OR ').join(parse(value) for value in parts(expression))+sql.SQL(')'));return self
 def order(self,k,*_):self.sort.append(sql.Identifier(k));return self
 def limit(self,n):self.maximum=n;return self
 def single(self):self.one=True;return self
 def where(self):return sql.SQL(' WHERE ')+sql.SQL(' AND ').join(self.filters) if self.filters else sql.SQL('')
 def execute(self):
  query=sql.SQL('SELECT * FROM public.{}').format(sql.Identifier(self.table))+self.where()
  if self.sort:query+=sql.SQL(' ORDER BY ')+sql.SQL(',').join(self.sort)
  if self.maximum:query+=sql.SQL(' LIMIT {}').format(sql.Literal(self.maximum))
  rows=run(query,self.args);return (rows[0] if rows else None) if self.one else rows
 def update(self,body):
  query=sql.SQL('UPDATE public.{} SET ').format(sql.Identifier(self.table))+sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(key)) for key in body)+self.where()+sql.SQL(' RETURNING *')
  return Result(run(query,list(body.values())+self.args))
class DB:
 def table(self,table):return Query(table)
db=DB();campus,closed,open_window=[str(uuid4()) for _ in range(3)];day=today_wat();fixed=datetime.combine(day,time(11),tzinfo=auto.WAT)
class Clock(datetime):
 @classmethod
 def now(cls,tz=None):return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
try:
 run("ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false")
 run("set local request.jwt.claims='{"+'"role":"service_role"'+"}'")
 run("insert into public.campuses(id,name,slug) values(%s,'[ROLLBACK] Automatic preparation',%s)",(campus,'auto-prep-'+campus))
 run("insert into public.feature_flags(feature_name,is_active,campus_id) values('auto_prepare_closed_windows',true,%s),('store_pickup',true,%s)",(campus,campus))
 run("insert into public.system_settings(key,value,campus_id,is_public) values('store_pickup_location','{\"name\":\"Test store\",\"address\":\"Test road\"}',%s,false)",(campus,))
 run("insert into public.ordering_windows(id,campus_id,date,opens_at,closes_at,capacity) values(%s,%s,%s,'09:00','10:00',20),(%s,%s,%s,'10:00','12:00',20)",(closed,campus,day,open_window,campus,day))
 cases={}
 for name,payment,window,scheduled,when,mode,test in [
  ('delivery','paid',closed,False,day,'off_campus',False),('pickup','paid',closed,False,day,'store_pickup',False),
  ('scheduled_today','paid',closed,True,day,'off_campus',False),('future','paid',closed,True,day+timedelta(days=1),'off_campus',False),
  ('unpaid','pending',closed,False,day,'off_campus',False),('live_window','paid',open_window,False,day,'off_campus',False),
  ('yesterday','paid',closed,False,day-timedelta(days=1),'off_campus',False),('test','paid',closed,False,day,'off_campus',True)]:
  oid=str(uuid4());cases[name]=oid
  run("insert into public.orders(id,campus_id,guest_email,payment_status,delivery_type,ordering_window_id,is_scheduled,scheduled_for,created_at,is_test,delivery_address_snapshot) values(%s,%s,'controlled@example.invalid',%s,%s,%s,%s,%s,%s,%s,'{\"line1\":\"Test road\",\"location_name\":\"Test store\"}')",(oid,campus,payment,mode,window,scheduled,datetime.combine(when,time(9),tzinfo=auto.WAT) if scheduled else None,datetime.combine(when,time(9),tzinfo=auto.WAT),test))
 run("update public.feature_flags set is_active=false where feature_name='store_pickup' and campus_id=%s",(campus,))
 app=Flask(__name__)
 with app.app_context(),patch.object(auto,'get_db',return_value=db),patch.object(auto,'datetime',Clock),patch.object(feature_flags,'get_db',return_value=db),patch.object(orders,'get_db',return_value=db),patch.object(orders,'_log_status_change'),patch('threading.Thread'):
  first=auto.prepare_closed_windows();second=auto.prepare_closed_windows()
 assert first[campus]=={'prepared':3,'skipped':0,'failed':0},first
 assert second[campus]['prepared']==0,second
 for name,oid in cases.items():
  row=run('select status,hp_earned,batch_id from public.orders where id=%s',(oid,))[0]
  assert row['status']==('preparing' if name in ('delivery','pickup','scheduled_today') else 'received'),(name,row)
  assert row['hp_earned']==0 and row['batch_id'] is None,(name,row)
 print('PASS: real producer/status/database loop: 3 due paid delivery/pickup/scheduled orders prepared; unpaid/future/live-window/yesterday/test excluded; repeat changes zero; no ready/dispatch/HP fabricated; all rolled back')
finally:c.rollback();c.close()
