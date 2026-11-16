"""Real overlapping sessions/process exit; disposable LOCAL PostgreSQL only."""
import os,sys,uuid,threading,subprocess,json
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
from psycopg2.extras import Json
DSN=os.environ.get('EVENT_RELIABILITY_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='reliability':raise SystemExit('Only a disposable local database named reliability is permitted.')
def uid():return str(uuid.uuid4())
def connect():
 c=psycopg2.connect(DSN);c.set_client_encoding('UTF8')
 with c.cursor() as q:q.execute("set search_path=public,extensions;set statement_timeout='10s';set lock_timeout='8s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
 c.commit();return c

def sql(stmt,args=(),one=False):
 with connect() as c:
  with c.cursor() as q:
   q.execute(stmt,args)
   if q.description:return q.fetchone()[0] if one else q.fetchall()

def run(call):
 try:return {'ok':sql(*call,one=True)}
 except Exception as e:return {'error':str(e).splitlines()[0],'code':e.pgcode}

def race(calls):
 barrier=threading.Barrier(len(calls))
 def worker(call):barrier.wait(timeout=5);return run(call)
 with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(worker,calls))
C,A=uid(),uid()
sql("insert into campuses(id,name,slug) values(%s,'[LOCAL event operations] '||%s,'local-ops-'||%s)",(C,C,C))
sql("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(A,'local-'+A+'@example.invalid'))
sql("update profiles set role='admin',campus_id=%s where id=%s",(C,A))
sql("insert into feature_flags(feature_name,campus_id,is_active) values('events',%s,true),('hp_multiplier',%s,false)",(C,C))
COPY={'event_cancelled_title':'Cancelled: {title}','event_cancelled_body':'{title} cancelled. {reason}','event_rescheduled_title':'New date: {title}','event_rescheduled_body':'{title}: {date}, {venue}. {reason}'}
def fixture(pending=False):
 e,u,t=uid(),uid(),uid()
 sql("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(u,'local-'+u+'@example.invalid'))
 sql('update profiles set campus_id=%s where id=%s',(C,u))
 sql("insert into events(id,title,slug,location,starts_at,ends_at,campus_id,is_published,hp_per_attendee) values(%s,'Local event operations','local-'||%s,'Hall',now()-interval '1 hour',now()+interval '1 day',%s,true,50)",(e,e,C))
 sql("insert into event_tickets(id,event_id,user_id,status,payment_status,price_naira,wallet_amount_used,card_amount_used,payment_reference,campus_id) values(%s,%s,%s,%s,%s,100,%s,%s,%s,%s)",(t,e,u,'pending_payment' if pending else 'confirmed','pending' if pending else 'paid',20 if pending else 100,80 if pending else 0,'local-card-'+t if pending else None,C))
 return e,u,t

def operation(e,request,action,body=None):
 args={'reason':'Local controlled event operations test.','expected_updated_at':sql('select updated_at from events where id=%s',(e,),True).isoformat(),'_copy':COPY,**(body or {})}
 return ('select hg_change_event_operation(%s,%s,%s,%s,%s)',(A,e,request,action,Json(args)))
e,u,t=fixture();first=operation(e,uid(),'reschedule',{'starts_at':'2027-12-01T10:00:00+01:00','ends_at':'2027-12-01T12:00:00+01:00','location':'New hall'})
r=race([first]*6);assert all('ok' in x for x in r) and sum(not x['ok']['replayed'] for x in r)==1,r
assert sql('select count(*) from notifications where user_id=%s and type=\'event_rescheduled\'',(u,),True)==3
print('PASS six simultaneous identical reschedules: one operation/notice per channel; five receipt replays',flush=True)
version=sql('select updated_at from events where id=%s',(e,),True).isoformat()
calls=[operation(e,uid(),'reschedule',{'starts_at':f'2027-12-{day:02}T10:00:00+01:00','ends_at':f'2027-12-{day:02}T12:00:00+01:00','location':'Hall '+str(day),'expected_updated_at':version}) for day in (3,4,5,6)]
r=race(calls);assert sum('ok' in x for x in r)==1 and sum(x.get('code')=='40001' for x in r)==3,r
print('PASS four competing date changes: one winner; three stale versions rejected',flush=True)

# Cancellation versus a verified payment: both acquire event then ticket locks.
e,u,t=fixture(pending=True);cancel=operation(e,uid(),'cancel');payment=('select hg_pay_event_with_delivery(%s,\'paystack\',%s,80,\'{}\')',(t,'local-card-'+t))
r=race([cancel,payment]);assert all('ok' in x for x in r),r
assert sql('select payment_status from event_tickets where id=%s',(t,),True)=='refunded'
assert sql('select balance from wallets where user_id=%s',(u,),True)==100
assert sql('select count(*) from hg_internal.event_ticket_refunds where ticket_id=%s',(t,),True)==1
assert 'ok' in run(payment)
assert sql('select balance from wallets where user_id=%s',(u,),True)==100
print('PASS cancel/payment race and callback replay: one refund, wallet restored once, no usable ticket',flush=True)

for n in range(6):
 e,u,t=fixture();cancel=operation(e,uid(),'cancel');admit=('select hg_admit_event_ticket(%s,%s,%s,null,%s,50)',(e,t,A,C))
 r=race([cancel,admit]);assert any('ok' in x for x in r) and all(x.get('code')!='40P01' for x in r),r
 checked=sql('select count(*) from event_checkins where ticket_id=%s',(t,),True)
 refunded=sql('select count(*) from hg_internal.event_ticket_refunds where ticket_id=%s',(t,),True)
 assert checked+refunded==1,(r,checked,refunded)
 assert sql('select hp_balance from profiles where id=%s',(u,),True)==(50 if checked else 0)
print('PASS six cancel/admission races: used tickets retain admission; unused tickets refund; never both',flush=True)

e,u,t=fixture();cancel=operation(e,uid(),'cancel');params=list(cancel[1]);params[-1]=params[-1].adapted
child="""import os,json,psycopg2
from psycopg2.extras import Json
c=psycopg2.connect(os.environ['EVENT_RELIABILITY_TEST_DSN']);q=c.cursor();q.execute("select set_config('request.jwt.claims','{\\\"role\\\":\\\"service_role\\\"}',true)")
p=json.loads(os.environ['LOCAL_OPERATION']);p[-1]=Json(p[-1]);q.execute('select hg_change_event_operation(%s,%s,%s,%s,%s)',p);q.fetchone();os._exit(0)
"""
subprocess.run([sys.executable,'-c',child],env={**os.environ,'LOCAL_OPERATION':json.dumps(params)},check=True,timeout=15)
assert sql('select balance from wallets where user_id=%s',(u,),True)==0
assert sql('select count(*) from hg_internal.event_ticket_refunds where ticket_id=%s',(t,),True)==0
assert sql("select coalesce(metadata->>'lifecycle_status','') from events where id=%s",(e,),True)!='cancelled'
assert sql("select count(*) from notifications where user_id=%s and type='event_cancelled'",(u,),True)==0
first=run(cancel);again=run(cancel);assert first['ok']['refunds']==1 and again['ok']['replayed']
assert sql('select balance from wallets where user_id=%s',(u,),True)==100
print('PASS client process exits before cancellation commit: no partial refund, status or notice; fresh session retry commits once',flush=True)
print('All synthetic fixtures are confined to the disposable local reliability database.',flush=True)
