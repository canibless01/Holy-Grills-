"""Competing explicit resend requests; disposable local reliability DB only."""
import os,uuid,threading
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('EVENT_RELIABILITY_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='reliability':raise SystemExit('Only isolated local reliability DB is allowed')
def run(query,args=(),fetch=False):
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:
   q.execute("set search_path=public,extensions;set statement_timeout='8s';set lock_timeout='6s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)");q.execute(query,args)
   if fetch:return q.fetchone()[0]
C,E,T=[str(uuid.uuid4()) for _ in range(3)]
run("insert into campuses(id,name,slug) values(%s,'[LOCAL] Resend','local-'||%s)",(C,C))
run("insert into events(id,title,slug,location,starts_at,ends_at,is_published,campus_id) values(%s,'[LOCAL] Resend','local-'||%s,'Hall',now(),now()+interval '1 day',true,%s)",(E,E,C))
run("insert into event_tickets(id,event_id,is_guest,guest_email,status,payment_status,campus_id) values(%s,%s,true,'guest@example.invalid','confirmed','not_required',%s)",(T,E,C))
gate=threading.Barrier(4)
def submit(_):
 gate.wait()
 try:return run("select hg_resend_event_ticket(%s,%s,%s,null,'guest@example.invalid',false,'Ticket','Confirmed')",(E,T,str(uuid.uuid4())),True)['state']
 except psycopg2.Error as exc:
  assert 'HG_TICKET_RESEND_COOLDOWN' in str(exc);return 'cooldown'
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,range(4)))
assert results.count('queued')==1 and results.count('cooldown')==3,results
assert run("select count(*) from notification_deliveries where dispatch_payload->>'ticket_id'=%s",(T,),True)==1
print('PASS four competing different resend requests: one queued receipt and three durable cooldown rejections')
