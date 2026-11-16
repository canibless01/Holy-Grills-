"""Explicit local database only. Race real creation guard against intent closure."""
import os,uuid,threading
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ['HG_TEST_PG_DSN'];cfg=parse_dsn(DSN)
assert cfg.get('host') in ('127.0.0.1','localhost') and cfg.get('dbname')=='hg_ops'
def db():
 c=psycopg2.connect(DSN);c.cursor().execute("set request.jwt.claims='{\"role\":\"service_role\"}'");c.commit();return c
u,campus,raw=str(uuid.uuid4()),str(uuid.uuid4()),str(uuid.uuid4());key='v2:'+uuid.uuid4().hex+uuid.uuid4().hex
setup=db();q=setup.cursor();q.execute("insert into campuses(id,name,slug) values(%s,'Local closure race',%s)",(campus,'local-'+campus));q.execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(u,'local-'+u+'@example.invalid'));q.execute('update profiles set campus_id=%s where id=%s',(campus,u));setup.commit()
a,b=db(),db();a.cursor().execute('select hg_abandon_checkout(%s,%s,%s,%s)',(u,campus,key,raw))
started=threading.Event();done=threading.Event();results=[]
def create_late():
 try:
  cursor=b.cursor();started.set();cursor.execute("select hg_create_order_atomic(p_user_id=>%s,p_guest_name=>NULL,p_guest_email=>NULL,p_guest_phone=>NULL,p_claim_token=>NULL,p_subtotal=>0,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>0,p_delivery_type=>'on_campus',p_delivery_location_id=>NULL,p_delivery_location_lat=>NULL,p_delivery_location_lon=>NULL,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>NULL,p_squad_name=>NULL,p_notes=>NULL,p_idempotency_key=>%s,p_promo_code_id=>NULL,p_items=>'[]')",(u,key));results.append(cursor.fetchone()[0]);b.commit()
 finally:done.set()
t=threading.Thread(target=create_late);t.start();assert started.wait(2);assert not done.wait(.15),'Creation must wait for shared intent lock'
a.commit();assert done.wait(5);t.join();assert results==[{'error':'checkout_intent_closed'}],results
q.execute('select count(*) from orders where idempotency_key=%s',(key,));assert q.fetchone()[0]==0
for c in (a,b,setup):c.close()
print('PASS actual concurrent SQL: closed intent wins against delayed creation, no order or debit created. Local fixtures only.')
