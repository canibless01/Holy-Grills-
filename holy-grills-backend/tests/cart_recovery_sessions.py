"""Independent local sessions. Explicit disposable DB only; no provider calls."""
import os,uuid,threading
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ['HG_TEST_PG_DSN'];parts=parse_dsn(DSN)
assert parts.get('host') in ('127.0.0.1','localhost') and parts.get('dbname')=='hg_ops','Disposable local hg_ops database required'
def connect():
 c=psycopg2.connect(DSN);c.cursor().execute("set request.jwt.claims='{\"role\":\"service_role\"}'");c.commit();return c
def uid():return str(uuid.uuid4())
c=connect();q=c.cursor();campus,owner,order,cart=uid(),uid(),uid(),uid()
q.execute("insert into campuses(id,name,slug) values(%s,'[LOCAL only] Cart concurrency',%s)",(campus,'local-'+campus))
q.execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(owner,'local-'+owner+'@example.invalid'))
q.execute("update profiles set campus_id=%s,push_enabled=false,email_notifications=true where id=%s",(campus,owner))
q.execute("insert into feature_flags(feature_name,campus_id,is_active) values('abandoned_cart_nudge',%s,true)",(campus,))
q.execute("insert into orders(id,user_id,campus_id,payment_status,created_at) values(%s,%s,%s,'pending',now()-interval '40 minutes')",(order,owner,campus))
q.execute("insert into abandoned_carts(id,user_id,campus_id,last_active_at,cart_payload) values(%s,%s,%s,now()-interval '40 minutes',jsonb_build_object('pending_order_id',%s::text))",(cart,owner,campus,order));c.commit()
statement="select hg_capture_cart_recovery_step(%s,0,now()+interval '1 hour')"
a,b=connect(),connect();a.cursor().execute(statement,(cart,));started=threading.Event();finished=threading.Event();result=[]
def second():
 try:
  started.set();cursor=b.cursor();cursor.execute(statement,(cart,));result.append(cursor.fetchone()[0]);b.commit()
 finally:finished.set()
thread=threading.Thread(target=second);thread.start();assert started.wait(2);assert not finished.wait(.15),'Second session must wait for same-cart lock'
a.rollback();assert finished.wait(5);thread.join();assert result[0]['saved'],result
q.execute("select count(*) from hg_internal.cart_recovery_steps where cart_id=%s",(cart,));assert q.fetchone()[0]==1
q.execute("select count(*) from notifications where reference_id=%s",(cart,));assert q.fetchone()[0]==2
q.execute(statement,(cart,));assert q.fetchone()[0]['reason']=='already_saved';c.rollback()
for conn in (a,b,c):conn.close()
print('PASS independent sessions: losing process rollback releases the claim; one email+inbox step commits; committed-response retry creates no extra notice. Local fixtures only.')
