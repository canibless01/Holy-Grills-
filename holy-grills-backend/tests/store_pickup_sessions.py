"""Actual concurrent collection and HP replay in the disposable loopback database only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import json
import psycopg2

DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent'
campus,user,order=[str(uuid4()) for _ in range(3)]
def connect():
 c=psycopg2.connect(DSN);c.cursor().execute("set request.jwt.claims='{"+'"role":"service_role"'+"}'");return c
setup=connect();q=setup.cursor()
try:
 q.execute('insert into public.campuses(id,name,slug) values(%s,%s,%s)',(campus,'[AUDIT disposable] Pickup concurrency','audit-pickup-'+campus))
 q.execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(user,'pickup-'+user+'@example.invalid'))
 q.execute("insert into public.profiles(id,email,campus_id,is_active,next_order_hp_multiplier) values(%s,%s,%s,true,1) on conflict(id) do update set campus_id=excluded.campus_id,is_active=true,next_order_hp_multiplier=1",(user,'pickup-'+user+'@example.invalid',campus))
 q.execute("insert into public.system_settings(key,value,campus_id,is_public) values('store_pickup_location',%s,%s,false)",(json.dumps({'name':'Disposable store','address':'Test road'}),campus))
 q.execute("insert into public.feature_flags(feature_name,is_active,campus_id) values('store_pickup',true,%s)",(campus,))
 q.execute("insert into public.orders(id,user_id,campus_id,payment_status,delivery_type,delivery_address_snapshot) values(%s,%s,%s,'paid','store_pickup','{\"line1\":\"Test road\",\"location_name\":\"Disposable store\"}')",(order,user,campus))
 q.execute("update public.orders set status='preparing' where id=%s",(order,));q.execute("update public.orders set status='ready' where id=%s",(order,));setup.commit()
 barrier=Barrier(2)
 def collect(_):
  c=connect();cur=c.cursor();barrier.wait()
  try:
   cur.execute("update public.orders set status='delivered',delivered_at=now() where id=%s and status='ready' returning id",(order,));changed=cur.rowcount;c.commit()
   cur.execute("select public.hg_credit_delivery_hp_atomic(%s,%s,10,'ember','food_order',1,10)",(order,user));result=cur.fetchone()[0];c.commit();return changed,result
  finally:c.close()
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(collect,range(2)))
 assert sorted(r[0] for r in results)==[0,1],results
 assert all(not r[1].get('error') for r in results),results
 q.execute('select hp_earned from public.orders where id=%s',(order,));assert q.fetchone()[0]==10
 q.execute("select count(*) from public.order_status_logs where order_id=%s and status='delivered' and not(metadata ? 'delivery_reward_recovery')",(order,));assert q.fetchone()[0]==1
 q.execute('select hp_balance from public.profiles where id=%s',(user,));assert q.fetchone()[0]==10
 print('PASS: two concurrent collection requests; one transition; one status log; HP 10 credited once; replay recovered without another credit')
finally:
 setup.rollback();q=setup.cursor()
 q.execute('delete from public.order_status_logs where order_id=%s',(order,));q.execute('delete from public.hp_transactions where user_id=%s',(user,));q.execute('delete from public.orders where id=%s',(order,));q.execute('delete from public.system_settings where campus_id=%s',(campus,));q.execute('delete from public.feature_flags where campus_id=%s',(campus,));q.execute('delete from public.profiles where id=%s',(user,));q.execute('delete from auth.users where id=%s',(user,));q.execute('delete from public.campuses where id=%s',(campus,));setup.commit();setup.close()
