"""Competing guest HP claims/process exit. Disposable LOCAL DB only."""
import os,sys,uuid,subprocess,threading
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('EVENT_RELIABILITY_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='reliability':raise SystemExit('Only isolated local reliability DB is allowed')
def sql(statement,args=(),one=False):
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:
   q.execute("set search_path=public,extensions;set statement_timeout='8s';set lock_timeout='6s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
   q.execute(statement,args)
   if q.description:return q.fetchone()[0] if one else q.fetchall()
def uid():return str(uuid.uuid4())
C,U,E,T=[uid() for _ in range(4)];email='local-guest-hp-'+U+'@example.invalid'
sql("insert into campuses(id,name,slug) values(%s,'[LOCAL] Guest HP','local-'||%s)",(C,C));sql("insert into feature_flags(feature_name,campus_id,is_active) values('events',%s,true),('hp_multiplier',%s,false)",(C,C))
sql("insert into auth.users(id,email,email_confirmed_at,raw_user_meta_data) values(%s,%s,now(),'{}')",(U,email));sql('update profiles set campus_id=%s,is_active=true where id=%s',(C,U))
def fixture(event,ticket):
 sql("insert into events(id,title,slug,location,starts_at,ends_at,is_published,campus_id,hp_per_attendee) values(%s,'[LOCAL] Guest HP','local-'||%s,'Hall',now()-interval '1 hour',now()+interval '1 day',true,%s,50)",(event,event,C));sql("insert into event_door_tokens(event_id,qr_token) values(%s,'local-door')",(event,))
 sql("insert into event_tickets(id,event_id,is_guest,guest_email,status,payment_status,campus_id) values(%s,%s,true,%s,'confirmed','not_required',%s)",(ticket,event,email,C));sql("select hg_admit_event_ticket(%s,%s,null,'local-door',%s,50)",(event,ticket,C))
fixture(E,T);gate=threading.Barrier(4)
def claim(_):gate.wait();return sql('select hg_claim_guest_attendance_hp(%s)',(U,),True)
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(claim,range(4)))
assert sum(r['claimed'] for r in results)==1,results
assert sql("select count(*) from hp_transactions where user_id=%s and reference_type='event' and reference_id=%s",(U,E),True)==1
E2,T2=uid(),uid();fixture(E2,T2)
code="""import os,psycopg2
c=psycopg2.connect(os.environ['EVENT_RELIABILITY_TEST_DSN']);q=c.cursor();q.execute(\"select set_config('request.jwt.claims','{\\\"role\\\":\\\"service_role\\\"}',false)\");q.execute('select hg_claim_guest_attendance_hp(%s)',(os.environ['GUEST_HP_ACTOR'],));print('CLAIMED_UNCOMMITTED',flush=True);input()
"""
child=subprocess.Popen([sys.executable,'-c',code],env=dict(os.environ,GUEST_HP_ACTOR=U),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 assert child.stdout.readline().strip()=='CLAIMED_UNCOMMITTED'
 child.kill();child.wait(timeout=5)
 assert sql('select user_id is null from event_tickets where id=%s',(T2,),True) is True
 assert sql('select hg_claim_guest_attendance_hp(%s)',(U,),True)['claimed']==1
 assert sql("select count(*) from hp_transactions where user_id=%s and reference_type='event' and reference_id=%s",(U,E2),True)==1
finally:
 if child.poll() is None:child.kill();child.wait(timeout=5)
print('PASS four competing guest HP claimers: one award; process exit rolls back ownership/ledger and recovery awards once')
