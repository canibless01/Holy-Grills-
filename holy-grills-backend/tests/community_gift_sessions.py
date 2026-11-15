"""Gift replay/conservation under contention. Disposable localhost DB only."""
import os,uuid,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('COMMUNITY_GIFT_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='hg_ops':raise SystemExit('Only disposable localhost hg_ops DB allowed')
def uid():return str(uuid.uuid4())
def sql(statement,args=(),one=True):
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:
   q.execute("set search_path=public,extensions;set statement_timeout='12s';set lock_timeout='10s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)")
   q.execute(statement,args)
   if q.description:return q.fetchone()[0] if one else q.fetchall()
C,A,B,HP,CASH=[uid() for _ in range(5)]
sql("insert into campuses(id,name,slug) values(%s,'[LOCAL] Gifts','local-'||%s)",(C,C))
for person in (A,B):
 sql("insert into profiles(id,email,role,campus_id,referral_code,is_active) values(%s,%s,'student',%s,%s,true)",(person,person+'@example.invalid',C,'GIFT'+person.replace('-','')[:16]))
 sql("insert into wallets(user_id,campus_id,currency,balance) values(%s,%s,'NGN',1000)",(person,C))
 sql("select record_hp_transaction_atomic(%s,100,'earn','active','seed','seed',%s,null,'Local seed',%s)",(person,uid(),C))
sql("insert into feature_flags(feature_name,campus_id,is_active) values('wallet_transfer',%s,true)",(C,))
def competing(kind):
 barrier=threading.Barrier(12)
 def call(_):
  barrier.wait()
  if kind=='hp':return sql("select hg_transfer_hp_gift(%s,%s,10,%s,'{\"anonymous\":true}')",(A,B,HP))
  return sql("select hg_wallet_transfer('send',%s,%s,jsonb_build_object('recipient_id',%s,'recipient_code',(select referral_code from profiles where id=%s),'amount_kobo',10000,'anonymous',true))",(A,CASH,B,B))
 with ThreadPoolExecutor(max_workers=12) as pool:return list(pool.map(call,range(12)))
competing('hp');competing('cash')
assert sql('select hp_balance from profiles where id=%s',(A,))==90
assert sql('select hp_balance from profiles where id=%s',(B,))==110
assert sql('select balance from wallets where user_id=%s',(A,))==900
assert sql('select balance from wallets where user_id=%s',(B,))==1100
assert sql("select count(*) from hp_transactions where reference_id=%s",(HP,))==2
assert sql('select count(*) from wallet_transactions where reference_id=%s',(CASH,))==2
assert sql('select hg_hp_gift_receipt(%s,%s)->>\'sender_name\'',(B,HP))=='Anonymous'
# Two fresh distinct debits each fit in isolation, but together exceed 90 HP.
barrier=threading.Barrier(2)
def overdraw(_):
 barrier.wait()
 try:sql("select hg_transfer_hp_gift(%s,%s,60,%s,'{}')",(A,B,uid()));return True
 except psycopg2.Error as e:
  assert 'insufficient_hp' in str(e);return False
with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(overdraw,range(2)))==1
assert sql('select sum(hp_balance) from profiles where id in(%s,%s)',(A,B))==200
print('PASS 12 simultaneous HP replays + 12 cash replays: one paired movement each; competing new HP debits cannot overdraw; balances conserved; anonymous receipt masked')
