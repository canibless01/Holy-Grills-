"""Independent local sessions only. Does not send mail or connect to production."""
import os,uuid,threading
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ['HG_TEST_PG_DSN'];parts=parse_dsn(DSN)
assert parts.get('host') in ('127.0.0.1','localhost') and parts.get('dbname')=='hg_ops','Disposable local hg_ops required'
def connect():
    c=psycopg2.connect(DSN);c.cursor().execute("set request.jwt.claims='{\"role\":\"service_role\"}'");c.commit();return c
def uid():return str(uuid.uuid4())
c=connect();q=c.cursor();campus,order,cart=uid(),uid(),uid();email='local-'+uid()+'@example.invalid'
q.execute("insert into campuses(id,name,slug) values(%s,'[LOCAL only] Guest recovery',%s)",(campus,'local-'+campus))
q.execute("insert into feature_flags(feature_name,campus_id,is_active) values('abandoned_cart_nudge',%s,true)",(campus,))
q.execute("insert into orders(id,campus_id,guest_email,guest_phone,claim_token,payment_status,status,created_at) values(%s,%s,%s,'08012345678',%s,'pending','received',now()-interval '40 minutes')",(order,campus,email,uid()))
q.execute("insert into abandoned_carts(id,campus_id,guest_email,guest_phone,last_active_at,cart_payload) values(%s,%s,%s,'08012345678',now()-interval '40 minutes',jsonb_build_object('pending_order_id',%s::text))",(cart,campus,email,order));c.commit()
statement="select hg_capture_guest_cart_recovery_step(%s,0,now()+interval '1 hour')"
a,b=connect(),connect();a.cursor().execute(statement,(cart,));result=[];errors=[];started=threading.Event();finished=threading.Event()
def second():
    try:
        started.set();cursor=b.cursor();cursor.execute(statement,(cart,));result.append(cursor.fetchone()[0]);b.commit()
    except Exception as e:errors.append(e)
    finally:finished.set()
t=threading.Thread(target=second);t.start();assert started.wait(2);assert not finished.wait(.15),'Second capture should wait for cart lock'
# A worker process losing its transaction must not leave a phantom email/step.
a.close();assert finished.wait(5);t.join();assert not errors,errors;assert result[0]['saved'],result
q.execute("select count(*) from hg_internal.cart_recovery_steps where cart_id=%s",(cart,));assert q.fetchone()[0]==1
q.execute("select count(*) from notification_deliveries where dispatch_payload->>'cart_id'=%s",(cart,));assert q.fetchone()[0]==1
q.execute(statement,(cart,));assert not q.fetchone()[0]['saved'];c.commit()
b.close();c.close();print('PASS: independent guest captures serialize; precommit process loss rolls back; one durable email and one saved step; replay does not duplicate')
