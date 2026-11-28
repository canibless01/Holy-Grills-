"""Independent sessions against an isolated local schema copy, never production.

Requires current table shapes/checks/indexes and relevant application functions.
No provider calls or HTTP application wakes. Fixtures are removed in finally.
"""
import json,os,subprocess,sys,threading,uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('AMBASSADOR_TEST_DSN','host=127.0.0.1 port=55439 dbname=ambassador_reliability user=postgres password=local-test')
parsed=parse_dsn(DSN)
if parsed.get('host') not in ('127.0.0.1','localhost') or parsed.get('dbname')!='ambassador_reliability':
 raise SystemExit('Only an isolated localhost database named ambassador_reliability is allowed.')
def connect():
 c=psycopg2.connect(DSN)
 with c.cursor() as q:q.execute("SET statement_timeout='10s';SET lock_timeout='8s';SET request.jwt.claims='{\"role\":\"service_role\"}'")
 c.commit();return c
def sql(statement,args=(),one=False):
 c=connect()
 try:
  with c.cursor() as q:
   q.execute(statement,args);result=(q.fetchone()[0] if one else q.fetchall()) if q.description else None
  c.commit();return result
 finally:c.close()
def run(statement,args=()):
 try:return {'ok':sql(statement,args,True)}
 except psycopg2.Error as e:return {'error':e.diag.message_primary,'code':e.pgcode}
def race(calls):
 barrier=threading.Barrier(len(calls))
 def worker(call):barrier.wait(timeout=10);return run(*call)
 with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(worker,calls))
def uid():return str(uuid.uuid4())
C,A,U,M,CLAIM=[uid() for _ in range(5)]
def grant(intent,amount=50,month='2026-01',claim=None,override=False,category='hp'):
 return ('SELECT hg_issue_ambassador_grant_atomic(%s,%s,%s,%s,%s,%s,14,1,%s,%s,%s,%s)',
  (A,U,category,amount,month,'Local reward '+month,'milestone' if claim else 'manual',claim,override,intent))
def hp():return sql('SELECT hp_balance FROM profiles WHERE id=%s',(U,),True)
def counter(table,where='true',args=()):return sql('SELECT count(*) FROM '+table+' WHERE '+where,args,True)
try:
 sql("INSERT INTO campuses(id,name,slug) VALUES(%s,'[LOCAL reliability] Ambassador','local-'||%s)",(C,C))
 for user,role in ((A,'super_admin'),(U,'student')):
  sql("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,'{}')",(user,'local-'+user+'@example.invalid'))
  sql('UPDATE profiles SET campus_id=%s,role=%s,is_active=true,push_enabled=true WHERE id=%s',(C,role,user))
 sql('INSERT INTO ambassadors(profile_id,campus_id,tagged_by) VALUES(%s,%s,%s)',(U,C,A))
 sql('INSERT INTO wallets(user_id,balance,campus_id) VALUES(%s,1000,%s)',(U,C))
 sql('INSERT INTO notification_preferences(user_id,hp_updates,push_enabled) VALUES(%s,true,true)',(U,))
 intent=uid();results=race([grant(intent)]*8)
 assert all('ok' in r and r['ok'].get('id') for r in results),results
 assert sum(not r['ok']['idempotent'] for r in results)==1
 receipt=results[0]['ok']['id']
 for channel in ('in_app','push'):
  expected=str(uuid.uuid5(uuid.NAMESPACE_URL,f'holy-grills:request-notification:{U}:ambassador_grant_issued:ambassador_grant:{receipt}:{channel}'))
  assert counter('notifications','id=%s',(expected,))==1
 assert hp()==50 and counter('ambassador_grants','ambassador_id=%s',(U,))==1
 assert counter('notifications','reference_id=%s',(receipt,))==2 and counter('notification_deliveries','user_id=%s',(U,))==1
 print('PASS eight identical grant requests: one award, one receipt, two channel notices, one queued push',flush=True)
 before=hp();results=race([grant(uid(),month='2026-02') for _ in range(8)])
 assert all('ok' in r for r in results),results
 assert sum('id' in r['ok'] for r in results)==1 and sum(r['ok'].get('error')=='duplicate_monthly_grant' for r in results)==7
 assert hp()==before+50
 print('PASS competing monthly grants: exactly one award; seven explicit duplicate refusals',flush=True)
 sql("INSERT INTO ambassador_milestones(id,campus_id,metric,threshold,reward_type,reward_amount,created_by) VALUES(%s,%s,'orders',1,'hp',50,%s)",(M,C,A))
 sql("INSERT INTO ambassador_milestone_claims(id,milestone_id,ambassador_id,period_month) VALUES(%s,%s,%s,'2026-03')",(CLAIM,M,U))
 before=hp();results=race([grant(uid(),amount=25+i,month='2026-03',claim=CLAIM,override=True) for i in range(8)])
 winner=[r['ok'] for r in results if 'ok' in r]
 assert len(winner)==1 and all(r.get('error')=='ambassador_claim_already_issued' for r in results if 'error' in r),results
 assert hp()==before+float(winner[0]['amount']) and counter('ambassador_grants','milestone_claim_id=%s',(CLAIM,))==1
 assert sql('SELECT grant_id::text FROM ambassador_milestone_claims WHERE id=%s',(CLAIM,),True)==winner[0]['id']
 print('PASS changed-configuration/override milestone race: one immutable claim reward',flush=True)
 # Kill a separate client after grant + notices ran but before COMMIT.
 crash_intent=uid();before=hp();before_notices=counter('notifications','user_id=%s',(U,))
 statement,args=grant(crash_intent,month='2026-04',override=True)
 child="""import json,os,psycopg2
c=psycopg2.connect(os.environ['AMBASSADOR_TEST_DSN']);q=c.cursor();q.execute("SET request.jwt.claims='{\\\"role\\\":\\\"service_role\\\"}'")
statement,args=json.loads(os.environ['LOCAL_GRANT_CALL']);q.execute(statement,args);q.fetchone();os._exit(0)
"""
 subprocess.run([sys.executable,'-c',child],env={'PATH':os.environ['PATH'],'AMBASSADOR_TEST_DSN':DSN,'LOCAL_GRANT_CALL':json.dumps([statement,args])},check=True,timeout=15)
 assert hp()==before and counter('ambassador_grants','idempotency_key=%s',(crash_intent,))==0 and counter('notifications','user_id=%s',(U,))==before_notices
 committed=run(statement,args)['ok'];replayed=run(statement,args)['ok']
 assert committed['id']==replayed['id'] and replayed['idempotent'] and hp()==before+50
 notice=sql("SELECT id::text FROM notifications WHERE reference_id=%s AND channel='push'",(committed['id'],),True)
 assert notice in sql('SELECT hg_due_notification_dispatch(100)',one=True)
 print('PASS process exit rolls back award and notices; committed response loss replays without new HP and is recoverable without Python wake',flush=True)
 results=race([('SELECT hg_claim_notification_dispatch_v2(%s)',(notice,))]*8)
 assert sum(r.get('ok',{}).get('state')=='claimed' for r in results)==1,results
 assert all(r.get('ok',{}).get('state') in ('claimed','busy') for r in results),results
 print('PASS eight dispatch workers claim the saved reward push once',flush=True)
 # Last-use meal reservation. This targets the entitlement helper; the full
 # checkout wallet/benefit loop has separate Supabase rollback acceptance.
 meal=run(*grant(uid(),amount=3000,month='2026-05',category='meal_discount'))['ok']['meal_discount_id']
 orders=[]
 for _ in range(8):
  order=uid();orders.append(order)
  sql("INSERT INTO orders(id,user_id,campus_id,subtotal,delivery_fee,discount_amount,total_amount,status,payment_status) VALUES(%s,%s,%s,4500,500,3000,2000,'received','paid')",(order,U,C))
 def reserve(order):return ('SELECT hg_redeem_ambassador_meal_discount(%s,%s,%s,3000,NULL)',(meal,order,U))
 results=race([reserve(order) for order in orders]);successful=[orders[i] for i,r in enumerate(results) if 'ok' in r]
 assert len(successful)==1 and all(r.get('error')=='meal_discount_no_uses_left' for r in results if 'error' in r),results
 assert sql('SELECT uses_remaining FROM ambassador_meal_discounts WHERE id=%s',(meal,),True)==0
 original=successful[0]
 results=race([('SELECT hg_restore_ambassador_meal_discount(%s)',(original,))]*8)
 assert sum(r.get('ok',{}).get('restored',False) for r in results)==1
 assert sql('SELECT uses_remaining FROM ambassador_meal_discounts WHERE id=%s',(meal,),True)==1
 print('PASS last-use meal race and simultaneous restoration: one reservation and one restored use',flush=True)
 # Restore and spend compete; available uses plus live reservations conserve 1.
 for n in range(6):
  old,new=uid(),uid()
  for order in (old,new):sql("INSERT INTO orders(id,user_id,campus_id,subtotal,delivery_fee,total_amount,status,payment_status) VALUES(%s,%s,%s,4500,500,5000,'received','paid')",(order,U,C))
  assert 'ok' in run(*reserve(old))
  results=race([('SELECT hg_restore_ambassador_meal_discount(%s)',(old,)),reserve(new)])
  assert all(r.get('code')!='40P01' for r in results),results
  uses=sql('SELECT uses_remaining FROM ambassador_meal_discounts WHERE id=%s',(meal,),True)
  active=counter('ambassador_meal_discount_redemptions','discount_id=%s AND restored_at IS NULL',(meal,))
  assert uses+active==1 and uses>=0
  if active:run('SELECT hg_restore_ambassador_meal_discount(%s)',(new,))
 print('PASS six cancellation/restoration versus new-use races conserve the single entitlement',flush=True)
finally:
 # All identifiers belong to this local-only run. No remote DSN is accepted.
 sql('DELETE FROM notification_deliveries WHERE user_id=%s',(U,))
 sql('DELETE FROM notifications WHERE user_id=%s',(U,))
 for table,key in [('ambassador_meal_discount_redemptions','ambassador_id'),('ambassador_meal_discounts','ambassador_id'),('ambassador_grants','ambassador_id'),('ambassador_milestone_claims','ambassador_id'),('free_side_credits','user_id'),('hp_transactions','user_id'),('notification_preferences','user_id'),('wallets','user_id')]:sql('DELETE FROM '+table+' WHERE '+key+'=%s',(U,))
 for table in ('ambassador_milestones','orders'):sql('DELETE FROM '+table+' WHERE campus_id=%s',(C,))
 sql('DELETE FROM ambassadors WHERE profile_id=%s',(U,));sql('DELETE FROM admin_audit_logs WHERE actor_id=%s',(A,))
 sql('DELETE FROM profiles WHERE id IN(%s,%s)',(A,U));sql('DELETE FROM auth.users WHERE id IN(%s,%s)',(A,U));sql('DELETE FROM campuses WHERE id=%s',(C,))
