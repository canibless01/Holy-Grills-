"""Independent PostgreSQL sessions; ONLY an isolated local schema copy.
Run: EVENT_RELIABILITY_TEST_DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent' python tests/event_reliability_sessions.py
The database must contain the current application's tables/functions/triggers.
Never accepts a remote DB URL. No provider calls are made.
"""
import os,sys,time,uuid,subprocess,threading
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extras import Json
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('EVENT_RELIABILITY_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='reliability':
 raise SystemExit('Use an isolated local database named reliability; production connections are refused.')
def connect():
 c=psycopg2.connect(DSN);c.set_client_encoding('UTF8')
 with c.cursor() as q:q.execute("set search_path=public,extensions;set statement_timeout='8s';set lock_timeout='5s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
 c.commit();return c

def sql(statement,args=(),one=False):
 with connect() as c:
  with c.cursor() as q:
   q.execute(statement,args)
   if q.description:return q.fetchone()[0] if one else q.fetchall()

def uid():return str(uuid.uuid4())
C,U,O,A,E,T,G,R=[uid() for _ in range(8)]
sql("insert into campuses(id,name,slug) values(%s,'[LOCAL reliability] '||%s,'local-'||%s)",(C,C,C))
for person,role in [(U,'student'),(O,'event_organizer'),(A,'super_admin')]:
 sql("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(person,'local-'+person+'@example.invalid'))
 sql('update profiles set campus_id=%s,role=%s where id=%s',(C,role,person))
sql("insert into feature_flags(feature_name,campus_id,is_active) values('events',%s,true),('hp_multiplier',%s,false)",(C,C))
sql("insert into events(id,title,slug,location,starts_at,ends_at,campus_id,organizer_id,is_published,hp_per_attendee) values(%s,'Local reliability','local-'||%s,'FUTA',now()-interval '1 hour',now()+interval '1 day',%s,%s,true,50)",(E,E,C,O))
def ticket(member=True):
 t=uid()
 sql("insert into event_tickets(id,event_id,user_id,is_guest,guest_email,status,payment_status,campus_id) values(%s,%s,%s,%s,%s,'confirmed','paid',%s)",(t,E,U if member else None,not member,None if member else 'local-guest@example.invalid',C))
 return t
T=ticket();G=ticket(False)
def admit(t):return ('select hg_admit_event_ticket(%s,%s,%s,null,%s,50)',(E,t,O,C))
def run(stmt,args=(),delay=0):
 c=connect()
 try:
  with c.cursor() as q:
   q.execute(stmt,args);result=q.fetchone()[0]
   if delay:q.execute('select pg_sleep(%s)',(delay,))
  c.commit();return {'ok':result}
 except Exception as e:c.rollback();return {'error':str(e).splitlines()[0],'code':e.pgcode}
 finally:c.close()
def race(calls):
 barrier=threading.Barrier(len(calls))
 def worker(call):barrier.wait(timeout=5);return run(*call)
 with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(worker,calls))

results=race([admit(T)]*8)
assert all('ok' in r for r in results),results
assert sum(not r['ok']['replayed'] for r in results)==1,results
assert sql('select count(*) from event_checkins where ticket_id=%s',(T,),True)==1
assert sql("select count(*) from hp_transactions where user_id=%s and reference_type='event' and reference_id=%s",(U,E),True)==1
assert sql('select hp_balance from profiles where id=%s',(U,),True)==50
print('PASS 8 simultaneous member scans: one check-in, one 50HP credit; seven replay receipts',flush=True)
results=race([admit(G)]*8)
assert all('ok' in r and r['ok']['is_guest'] and r['ok']['hp_added_to_active']==0 for r in results),results
assert sum(not r['ok']['replayed'] for r in results)==1
print('PASS 8 simultaneous guest scans: one admission, no unowned HP',flush=True)

# Kill the client after the function returns but before COMMIT. PostgreSQL must
# roll back admission and HP even though all statements already ran.
crash_person=uid()
sql("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(crash_person,'local-'+crash_person+'@example.invalid'))
sql('update profiles set campus_id=%s where id=%s',(C,crash_person))
crash_ticket=uid()
sql("insert into event_tickets(id,event_id,user_id,status,payment_status,campus_id) values(%s,%s,%s,'confirmed','paid',%s)",(crash_ticket,E,crash_person,C))
child="""import os,psycopg2
c=psycopg2.connect(os.environ['EVENT_RELIABILITY_TEST_DSN'])
q=c.cursor();q.execute("select set_config('request.jwt.claims','{\\\"role\\\":\\\"service_role\\\"}',true)")
q.execute('select hg_admit_event_ticket(%s,%s,%s,null,%s,50)',os.environ['LOCAL_EVENT_ARGS'].split(','));q.fetchone()
os._exit(0)
"""
subprocess.run([sys.executable,'-c',child],env={**os.environ,'LOCAL_EVENT_ARGS':','.join((E,crash_ticket,O,C))},check=True,timeout=10)
assert sql('select count(*) from event_checkins where ticket_id=%s',(crash_ticket,),True)==0
assert sql('select hp_balance from profiles where id=%s',(crash_person,),True)==0
assert sql("select count(*) from hp_transactions where user_id=%s",(crash_person,),True)==0
assert run(*admit(crash_ticket))['ok']['replayed'] is False
assert sql('select hp_balance from profiles where id=%s',(crash_person,),True)==50
print('PASS process exit before commit: no partial admission; fresh session retries successfully',flush=True)
committed=ticket(False);first=run(*admit(committed))['ok'];replay=run(*admit(committed))['ok']
assert replay['replayed'] and first['checkin_id']==replay['checkin_id']
print('PASS committed response lost: new session returns the original receipt',flush=True)

# Race paid-ticket cancellation against admission. Whichever acquires the
# event lock first wins; the other must reject without a partial side effect.
for n in range(6):
 person=uid()
 sql("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(person,'local-'+person+'@example.invalid'))
 sql('update profiles set campus_id=%s where id=%s',(C,person))
 t=uid()
 sql("insert into event_tickets(id,event_id,user_id,status,payment_status,campus_id) values(%s,%s,%s,'confirmed','paid',%s)",(t,E,person,C))
 refund=('select hg_request_event_ticket_refund(%s,%s,%s,%s,%s)',(A,E,t,uid(),'Local reliability refund reason'))
 results=race([admit(t),refund]);ok=[r for r in results if 'ok' in r]
 assert len(ok)==1 and all(r.get('code')!='40P01' for r in results),results
 counts=sql('select (select count(*) from event_checkins where ticket_id=%s),(select count(*) from hg_internal.event_ticket_refunds where ticket_id=%s)',(t,t))[0]
 assert sum(counts)==1,counts
print('PASS 6 admission/refund races: one valid outcome, no double state or deadlock',flush=True)

# A separate ended event keeps organizer payouts independent of admission.
P,PT,PG=uid(),uid(),uid()
sql("insert into events(id,title,slug,location,starts_at,ends_at,campus_id,organizer_id,is_published) values(%s,'Local settlement','local-'||%s,'FUTA',now()-interval '2 days',now()-interval '1 day',%s,%s,true)",(P,P,C,O))
sql("insert into event_ticket_tiers(id,event_id,name,price_naira,capacity,campus_id) values(%s,%s,'Regular',1600,10,%s)",(PT,P,C))
sql('insert into hg_internal.event_organizer_terms(tier_id,event_id,organizer_amount,updated_by) values(%s,%s,1500,%s)',(PT,P,A))
sql("insert into event_tickets(id,event_id,tier_id,is_guest,guest_email,status,payment_status,campus_id) values(%s,%s,%s,true,'local-settlement@example.invalid','confirmed','paid',%s)",(PG,P,PT,C))
bank={'bank_name':'Local bank','account_name':'Local organizer','account_number':'0123456789'}
requests=[uid(),uid()]
def payout(r,action,body):return ('select hg_event_payout_action(%s,%s,%s,%s,%s)',(O if action=='request' else A,P,r,action,Json(body)))
results=race([payout(r,'request',bank) for r in requests]);success=[r['ok'] for r in results if 'ok' in r]
assert len(success)==1 and success[0]['amount']==1500,results
request=success[0]['id']
results=race([payout(request,'request',bank)]*4)
assert all(r.get('ok',{}).get('id')==request for r in results),results
assert sql('select sum(amount) from hg_internal.event_payout_requests where event_id=%s and state in (\'pending\',\'approved\')',(P,),True)==1500
results=race([payout(request,'approve',{})]*4)
assert all(r.get('ok',{}).get('state')=='approved' for r in results),results
results=race([payout(request,'paid',{'reference':'LOCAL-TRANSFER-'+P})]*4)
assert all(r.get('ok',{}).get('state')=='paid' for r in results),results
assert sql('select count(*) from hg_internal.event_payout_requests where event_id=%s and state=\'paid\'',(P,),True)==1
print('PASS competing payout requests reserve once; concurrent request/approval/payment retries preserve one transfer record',flush=True)
print('All fixtures remain ONLY in the disposable local reliability database; no production rows/provider calls.',flush=True)

# Notify records + provider-dispatch rows must survive independently of Python.
# Kill before COMMIT: neither submission nor notices can persist.
N=uid();copy={'title':'Event workspace update','body':'{title}: {status}. Open the event workspace for details.'}
draft={'title':'Local durable notice','location':'FUTA','starts_at':'2027-12-01T10:00:00+01:00','ends_at':'2027-12-01T12:00:00+01:00','capacity':10}
assert 'ok' in run('select hg_organizer_event_draft(%s,%s,\'create\',%s)',(O,N,Json(draft)))
child="""import os,psycopg2,json
c=psycopg2.connect(os.environ['EVENT_RELIABILITY_TEST_DSN']);q=c.cursor()
q.execute("select set_config('request.jwt.claims','{\\\"role\\\":\\\"service_role\\\"}',true)")
a=os.environ['LOCAL_EVENT_ARGS'].split(',')
q.execute("select hg_organizer_event_draft(%s,%s,'submit',%s)",(a[0],a[1],json.dumps({'_notice':{'title':'Event update','body':'{title}: {status}'}})));q.fetchone()
os._exit(0)
"""
subprocess.run([sys.executable,'-c',child],env={**os.environ,'LOCAL_EVENT_ARGS':','.join((O,N))},check=True,timeout=10)
assert sql("select review_status from events where id=%s",(N,),True)=='draft'
assert sql("select count(*) from notifications where metadata->>'organizer_event_id'=%s",(N,),True)==0
submit=('select hg_organizer_event_draft(%s,%s,\'submit\',%s)',(O,N,Json({'_notice':copy})))
results=race([submit]*4)
assert all(r.get('ok',{}).get('review_status')=='submitted' for r in results),results
assert sql("select count(*) from notifications where metadata->>'organizer_event_id'=%s and user_id=%s",(N,A),True)==2
assert sql("select count(*) from notification_deliveries where id in(select id from notifications where metadata->>'organizer_event_id'=%s and user_id=%s and channel='push')",(N,A),True)==1
review=('select hg_review_organizer_event(%s,%s,\'approve\',%s)',(A,N,Json({'notes':'Reviewed locally','_notice':copy})))
results=race([review]*4)
assert all(r.get('ok',{}).get('review_status')=='approved' for r in results),results
assert sql("select count(*) from notifications where metadata->>'organizer_event_id'=%s and user_id=%s and type='event_review_updated'",(N,O),True)==2
print('PASS atomic notices: process exit rolls back state+notice; concurrent submissions/reviews capture one notice/channel and one durable push; no Python wake required',flush=True)

push_id=sql("select id from notifications where metadata->>'organizer_event_id'=%s and user_id=%s and channel='push' limit 1",(N,O),True)
claim=('select hg_claim_notification_dispatch_v2(%s)',(push_id,))
results=race([claim]*8);claimed=[r['ok'] for r in results if r.get('ok',{}).get('state')=='claimed']
assert len(claimed)==1 and sum(r.get('ok',{}).get('state')=='busy' for r in results)==7,results
first=claimed[0]
assert run('select hg_begin_notification_dispatch(%s,%s,%s)',(push_id,first['token'],Json({'local':True})))['ok'] is True
sql("update notification_deliveries set dispatch=dispatch||jsonb_build_object('lease_until',now()-interval '1 second') where id=%s",(push_id,))
reclaimed=run(*claim)['ok'];assert reclaimed['state']=='claimed' and reclaimed['key']==first['key']
assert run('select hg_finish_notification_dispatch(%s,%s,%s)',(push_id,first['token'],Json({'state':'accepted'})))['ok'] is False
assert run('select hg_finish_notification_dispatch(%s,%s,%s)',(push_id,reclaimed['token'],Json({'state':'accepted'})))['ok'] is True
email_id=uid()
sql("insert into notifications(id,user_id,type,title,body,channel,metadata) values(%s,%s,'event_registered','Local ticket','Local recovery check','email','{\"_dispatch_version\":1}')",(email_id,U))
email_claim=run('select hg_claim_notification_dispatch_v2(%s)',(email_id,))['ok']
assert email_claim['state']=='claimed'
assert run('select hg_begin_notification_dispatch(%s,%s,%s)',(email_id,email_claim['token'],Json({'local':True})))['ok'] is True
sql("update notification_deliveries set dispatch=dispatch||jsonb_build_object('lease_until',now()-interval '1 second') where id=%s",(email_id,))
assert run('select hg_claim_notification_dispatch_v2(%s)',(email_id,))['ok']['state']=='uncertain'
print('PASS 8 competing dispatch workers: one lease; expired push reuses provider key, stale worker cannot finish; interrupted email handoff becomes uncertain instead of blind resend',flush=True)
