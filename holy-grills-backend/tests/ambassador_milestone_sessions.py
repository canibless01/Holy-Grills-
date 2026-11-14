"""Independent transaction races, interrupted writer and committed-response replay.
Runs only against the disposable localhost reliability database.
"""
import json,threading,uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg2
DSN='host=127.0.0.1 port=5547 dbname=reliability user=agent'
C,A=[str(uuid.uuid4()) for _ in range(2)]
def connect():
 c=psycopg2.connect(DSN)
 with c.cursor() as q:q.execute("set statement_timeout='12s';set lock_timeout='10s';set request.jwt.claims='{\"role\":\"service_role\"}'")
 c.commit();return c
V={'metric':'orders','threshold':7,'reward_type':'hp','reward_amount':50,'reward_uses':1,'validity_days':14,'auto_issue':False,'is_active':True}
def write(request,row=None,values=None,expected=None,commit=True):
 c=connect()
 try:
  with c.cursor() as q:
   q.execute('set local role service_role')
   q.execute('select hg_write_ambassador_milestone(%s,%s,%s,%s,%s::jsonb,%s,%s)',(A,request,row or request,C,json.dumps(values or V),expected,row is None));result=q.fetchone()[0]
  if commit:c.commit()
  else:c.rollback()
  return result
 except psycopg2.Error as e:return {'error':e.diag.message_primary}
 finally:c.close()
def race(jobs):
 barrier=threading.Barrier(len(jobs))
 def run(args):barrier.wait();return write(*args)
 with ThreadPoolExecutor(max_workers=len(jobs)) as pool:return list(pool.map(run,jobs))
c=connect()
try:
 with c.cursor() as q:
  q.execute("insert into campuses(id,name,slug) values(%s,'[LOCAL audit] Milestone','audit-'||%s)",(C,C))
  q.execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(A,'audit-'+A+'@example.invalid'))
  q.execute("update profiles set role='admin',is_active=true,campus_id=%s where id=%s",(C,A))
 c.commit()
 request=str(uuid.uuid4());result=race([(request,)]*6);assert all('milestone' in r for r in result),result
 assert len({r['milestone']['id'] for r in result})==1
 original=result[0]['milestone'];assert write(request)['milestone']==original
 result=race([(str(uuid.uuid4()),)]*2);assert all(r['milestone']['id']==request for r in result),result
 edits=race([(str(uuid.uuid4()),request,{'reward_amount':75},original['updated_at']),(str(uuid.uuid4()),request,{'reward_amount':100},original['updated_at'])]);assert sum('milestone' in r for r in edits)==1 and sum(r.get('error')=='HG_AMB_MILESTONE_STALE' for r in edits)==1,edits
 rollback_id=str(uuid.uuid4());assert 'milestone' in write(rollback_id,values={**V,'threshold':9},commit=False)
 with c.cursor() as q:q.execute('select count(*) from ambassador_milestones where id=%s',(rollback_id,));assert q.fetchone()[0]==0
 assert write(rollback_id,values={**V,'threshold':9})['milestone']['id']==rollback_id
 with c.cursor() as q:q.execute('select count(*) from ambassador_milestones where campus_id=%s',(C,));assert q.fetchone()[0]==2
 print(json.dumps({'same_intent_sessions':6,'different_intent_dedupe':True,'stale_edit_race':True,'rollback_retry':True,'committed_response_replay':True}))
finally:
 c.rollback()
 with c.cursor() as q:
  q.execute('delete from admin_audit_logs where actor_id=%s',(A,));q.execute('delete from ambassador_milestones where campus_id=%s',(C,));q.execute('delete from profiles where id=%s',(A,));q.execute('delete from auth.users where id=%s',(A,));q.execute('delete from campuses where id=%s',(C,))
 c.commit();c.close()
