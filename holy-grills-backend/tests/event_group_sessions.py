"""Concurrent actual group reservations/payment fanout; disposable loopback PG only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import json
import psycopg2
from psycopg2.extras import Json
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent'
C,U,V,E,E2,T,T2,T3=[str(uuid4()) for _ in range(8)]
def connect():
 c=psycopg2.connect(DSN);c.cursor().execute("set search_path=public,extensions;set request.jwt.claims='{\"role\":\"service_role\"}';set lock_timeout='8s';set statement_timeout='20s'");return c
setup=connect();q=setup.cursor()
def roster(tier_a,tier_b,prefix):return [{'name':'First attendee','email':prefix+'-a@example.invalid','phone':'08012345678','tier_id':tier_a,'answers':{'question':'First'}},{'name':'Second attendee','email':prefix+'-b@example.invalid','phone':'08012345678','tier_id':tier_b,'answers':{'question':'Second'}}]
def register(event,user,key,people,barrier):
 c=connect();cur=c.cursor();barrier.wait(timeout=15)
 try:
  cur.execute("select public.hg_create_event_group(%s,%s,%s,%s,'split',100,NULL,%s,%s)",(event,user,Json({'name':'Buyer','email':'buyer-'+user+'@example.invalid','phone':'08012345678'}),Json(people),key,'a'*64));result=cur.fetchone()[0];c.commit();return {'group':result}
 except psycopg2.Error as error:c.rollback();return {'error':error.diag.message_primary}
 finally:c.close()
try:
 q.execute("insert into campuses(id,name,slug) values(%s,'[LOCAL] Group concurrency',%s)",(C,'local-group-'+C))
 for user in (U,V):
  q.execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(user,'buyer-'+user+'@example.invalid'))
  q.execute("update profiles set campus_id=%s,is_active=true,role='student' where id=%s",(C,user));q.execute('insert into wallets(user_id,balance) values(%s,1000) on conflict(user_id) do update set balance=1000',(user,))
 q.execute("insert into feature_flags(feature_name,is_active,campus_id) values('events',true,%s)",(C,))
 for event,capacity in ((E,20),(E2,3)):
  q.execute("insert into events(id,title,slug,location,starts_at,ends_at,capacity,is_published,is_paid,campus_id) values(%s,'[LOCAL] Group race',%s,'Local hall',now()+interval '1 hour',now()+interval '3 hours',%s,true,true,%s)",(event,'local-group-'+event,capacity,C))
 for tier,event,price in ((T,E,100),(T2,E,200),(T3,E2,100)):
  q.execute("insert into event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,campus_id) values(%s,%s,'Local tier',%s,%s,%s)",(tier,event,price,price,C))
 setup.commit();barrier=Barrier(8);people=roster(T,T2,'same-'+E)
 with ThreadPoolExecutor(max_workers=8) as pool:responses=list(pool.map(lambda _:register(E,U,'same-intent-'+E,people,barrier),range(8)))
 assert all('group' in response for response in responses),responses
 ids={response['group']['id'] for response in responses};assert len(ids)==1;group=responses[0]['group'];gid=group['id']
 q.execute('select balance from wallets where user_id=%s',(U,));assert q.fetchone()[0]==900
 q.execute('select count(*) from event_tickets where group_id=%s',(gid,));assert q.fetchone()[0]==2
 barrier=Barrier(8)
 def settle(_):
  c=connect();cur=c.cursor();barrier.wait(timeout=15)
  try:cur.execute("select hg_pay_event_group(%s,%s,200,'{}')",(gid,group['payment_reference']));r=cur.fetchone()[0];c.commit();return r
  finally:c.close()
 with ThreadPoolExecutor(max_workers=8) as pool:paid=list(pool.map(settle,range(8)))
 assert all(row['payment_status']=='paid' for row in paid)
 q.execute('select count(*),sum(p.amount) from payments p join event_tickets t on t.id=p.ticket_id where t.group_id=%s',(gid,));assert q.fetchone()==(1,200)
 q.execute('select count(*) from notification_deliveries where id in(select id from event_tickets where group_id=%s)',(gid,));assert q.fetchone()[0]==2
 q.execute("select count(*) from notification_deliveries where id=%s and dispatch_payload->>'kind'='event_group_email'",(gid,));assert q.fetchone()[0]==1
 setup.commit();barrier=Barrier(2)
 with ThreadPoolExecutor(max_workers=2) as pool:capacity=list(pool.map(lambda entry:register(E2,entry[0],entry[1],roster(T3,T3,entry[1]),barrier),[(U,'capacity-one-'+E2),(V,'capacity-two-'+E2)]))
 assert sum('group' in item for item in capacity)==1 and sum('error' in item for item in capacity)==1,capacity
 q.execute('select count(*) from event_tickets where event_id=%s',(E2,));assert q.fetchone()[0]==2
 q.execute('select sum(balance) from wallets where user_id in(%s,%s)',(U,V));assert q.fetchone()[0]==1800
 print('PASS: 8 same-intent sessions = one group/two tickets/one wallet debit; 8 confirmations = allocated receipts and 2 durable emails once; competing two-person groups at capacity 3 = one full booking, no partial group or extra debit')
finally:
 setup.rollback();q=setup.cursor()
 q.execute('delete from notification_deliveries where campus_id=%s',(C,));q.execute('delete from payments where ticket_id in(select id from event_tickets where event_id in(%s,%s))',(E,E2));q.execute('delete from event_tickets where event_id in(%s,%s)',(E,E2));q.execute('delete from hg_internal.event_ticket_groups where event_id in(%s,%s)',(E,E2));q.execute('delete from event_ticket_tiers where event_id in(%s,%s)',(E,E2));q.execute('delete from events where id in(%s,%s)',(E,E2));q.execute('delete from feature_flags where campus_id=%s',(C,));q.execute('delete from wallet_transactions where user_id in(%s,%s)',(U,V));q.execute('delete from wallets where user_id in(%s,%s)',(U,V));q.execute('delete from profiles where id in(%s,%s)',(U,V));q.execute('delete from auth.users where id in(%s,%s)',(U,V));q.execute('delete from campuses where id=%s',(C,));setup.commit();setup.close()
