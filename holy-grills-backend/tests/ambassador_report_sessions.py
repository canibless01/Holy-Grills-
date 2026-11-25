"""Concurrent report capture proof; refuses remote databases and sends no mail."""
import os,threading,uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('HG_REPORT_TEST_DSN','host=127.0.0.1 port=55449 dbname=engagement user=postgres password=engagement-local')
p=parse_dsn(DSN)
if p.get('host') not in ('127.0.0.1','localhost') or p.get('dbname')!='engagement':raise SystemExit('Only isolated localhost engagement database is allowed')
def sql(statement,args=(),one=False):
 with psycopg2.connect(DSN) as conn:
  with conn.cursor() as cur:
   cur.execute("SET statement_timeout='10s'; SET lock_timeout='8s'; SET request.jwt.claims='{\"role\":\"service_role\"}'")
   cur.execute(statement,args)
   if cur.description:return cur.fetchone()[0] if one else cur.fetchall()
c,u=[str(uuid.uuid4()) for _ in range(2)]
try:
 sql("INSERT INTO campuses(id,name,slug,is_active) VALUES(%s,'Local report race',%s,true)",(c,'local-'+c))
 sql('INSERT INTO auth.users(id,email) VALUES(%s,%s)',(u,u+'@example.invalid'))
 sql("UPDATE profiles SET campus_id=%s,role='student',is_active=true,email_notifications=true WHERE id=%s",(c,u))
 sql("INSERT INTO ambassadors(profile_id,campus_id,status) VALUES(%s,%s,'active')",(u,c))
 barrier=threading.Barrier(6)
 def enqueue(_):
  barrier.wait(timeout=12)
  return sql("SELECT hg_queue_ambassador_report(%s,%s,'monthly',(date_trunc('month',now())-interval '1 month')::date,'Local report','Safe aggregate only')",(u,c),True)
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(enqueue,range(6)))
 assert sum(bool(x.get('queued')) for x in results)==1 and sum(bool(x.get('duplicate')) for x in results)==5,results
 assert sql('SELECT count(*) FROM hg_internal.ambassador_report_receipts WHERE user_id=%s',(u,),True)==1
 assert sql("SELECT count(*) FROM notification_deliveries WHERE user_id=%s AND dispatch_payload->'notification'->>'type'='ambassador_progress_report'",(u,),True)==1
 print('PASS six concurrent report captures create one private period receipt, one email and one outbox; no external send',flush=True)
finally:
 sql('DELETE FROM notification_deliveries WHERE user_id=%s',(u,));sql('DELETE FROM notifications WHERE user_id=%s',(u,));sql('DELETE FROM hg_internal.ambassador_report_receipts WHERE user_id=%s',(u,));sql('DELETE FROM ambassadors WHERE profile_id=%s',(u,));sql('DELETE FROM profiles WHERE id=%s',(u,));sql('DELETE FROM auth.users WHERE id=%s',(u,));sql('DELETE FROM campuses WHERE id=%s',(c,))
