"""Independent newsletter create sessions. Disposable local reliability DB only."""
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
C,A,R=[str(uuid.uuid4()) for _ in range(3)]
run("insert into campuses(id,name,slug) values(%s,'[LOCAL] Newsletter','local-'||%s)",(C,C));run("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(A,'local-newsletter-'+A+'@example.invalid'));run("update profiles set role='admin',campus_id=%s,is_active=true where id=%s",(C,A))
for shared in (True,False):
 gate=threading.Barrier(4)
 def queue(_):
  gate.wait()
  try:return run('select hg_queue_newsletter_campaign(%s,%s,%s,%s,%s)',(A,R if shared else str(uuid.uuid4()),C,'Shared' if shared else 'Different','Body'),True)['replayed']
  except psycopg2.Error as exc:
   assert 'HG_NEWSLETTER_DUPLICATE' in str(exc);return 'duplicate'
 with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(queue,range(4)))
 if shared:assert results.count(False)==1 and results.count(True)==3,results
 else:assert results.count(False)==1 and results.count('duplicate')==3,results
assert run('select count(*) from newsletter_campaigns where campus_id=%s',(C,),True)==2
print('PASS same UUID: one insert + three replays; different UUIDs/identical content: one insert + three duplicate rejections')
