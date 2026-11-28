"""Real PostgreSQL + real worker, substituted provider. LOCAL DB only."""
import os,uuid,json,time,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from flask import Flask
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import parse_dsn
from app.services import newsletter_service as service
DSN=os.environ.get('EVENT_RELIABILITY_TEST_DSN','')
if not DSN or parse_dsn(DSN).get('host') not in ('127.0.0.1','localhost') or parse_dsn(DSN).get('dbname')!='reliability':raise SystemExit('Only isolated local reliability DB is allowed')
def execute(query,args=(),rows=False):
 with psycopg2.connect(DSN) as c:
  with c.cursor() as q:
   q.execute("set search_path=public,extensions;set statement_timeout='8s';set lock_timeout='6s';select set_config('request.jwt.claims','{\"role\":\"service_role\"}',false)");q.execute(query,args)
   if q.description:
    names=[d[0] for d in q.description];result=[dict(zip(names,row)) for row in q.fetchall()];return result if rows else (result[0][names[0]] if result else None)
class Query:
 def __init__(self,table):self.table=table;self.columns=sql.SQL('*');self.filters=[];self.params=[];self.ordering=[];self.maximum=None
 def select(self,columns):self.columns=sql.SQL(',').join(sql.Identifier(c) for c in columns.split(',')) if columns!='*' else sql.SQL('*');return self
 def compare(self,column,operator,value):self.filters.append(sql.SQL('{} '+operator+' %s').format(sql.Identifier(column)));self.params.append(value);return self
 def eq(self,k,v):return self.compare(k,'=',v)
 def lt(self,k,v):return self.compare(k,'<',v)
 def lte(self,k,v):return self.compare(k,'<=',v)
 def gt(self,k,v):return self.compare(k,'>',v)
 def in_(self,k,values):self.filters.append(sql.SQL('{} = ANY(%s'+('::uuid[]' if k.endswith('_id') else '')+')').format(sql.Identifier(k)));self.params.append(values);return self
 def is_(self,k,v):assert v=='null';self.filters.append(sql.SQL('{} IS NULL').format(sql.Identifier(k)));return self
 def order(self,k,ascending=True):self.ordering.append(sql.SQL('{} '+('ASC' if ascending else 'DESC')).format(sql.Identifier(k)));return self
 def limit(self,n):self.maximum=n;return self
 def tail(self):return sql.SQL(' WHERE ')+sql.SQL(' AND ').join(self.filters) if self.filters else sql.SQL('')
 def execute(self):
  query=sql.SQL('SELECT {} FROM public.{}').format(self.columns,sql.Identifier(self.table))+self.tail()
  if self.ordering:query+=sql.SQL(' ORDER BY ')+sql.SQL(',').join(self.ordering)
  if self.maximum is not None:query+=sql.SQL(' LIMIT {}').format(sql.Literal(self.maximum))
  return execute(query,self.params,True)
 def update(self,body):
  query=sql.SQL('UPDATE public.{} SET ').format(sql.Identifier(self.table))+sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in body)+self.tail()+sql.SQL(' RETURNING *')
  return execute(query,list(body.values())+self.params,True)
class DB:
 def table(self,name):return Query(name)
 def rpc(self,name,body):return execute(sql.SQL('SELECT public.{}({})').format(sql.Identifier(name),sql.SQL(',').join(sql.SQL('{}=>%s').format(sql.Identifier(k)) for k in body)),list(body.values()))
db=DB();app=Flask(__name__);app.config.update(SECRET_KEY='controlled',FRONTEND_URL='https://holygrills.online')
C,A,S1,S2=[str(uuid.uuid4()) for _ in range(4)]
execute("insert into campuses(id,name,slug) values(%s,'[LOCAL] Newsletter worker '||%s,'local-'||%s)",(C,C,C));execute("insert into auth.users(id,email,raw_user_meta_data) values(%s,%s,'{}')",(A,'local-worker-'+A+'@example.invalid'));execute("update profiles set role='admin',campus_id=%s,is_active=true where id=%s",(C,A))
for sub in (S1,S2):execute("insert into newsletter_subscriptions(id,email,campus_id,is_confirmed,created_at) values(%s,%s,%s,true,now()-interval '1 day')",(sub,sub+'@example.invalid',C))
def campaign():
 cid=str(uuid.uuid4());execute("insert into newsletter_campaigns(id,campus_id,created_by,subject,body,status) values(%s,%s,%s,'Subject','Body','sending')",(cid,C,A));return execute('select * from newsletter_campaigns where id=%s',(cid,),True)[0]
def worker(c,sender):
 with app.app_context(),patch.object(service,'_compose',return_value=('Subject','Body',None)),patch.object(service,'SEND_INTERVAL_SECONDS',0):return service._process_one(db,c,time.monotonic()+30,sender)
# Cached subscriber page is intentionally invalidated between provider calls.
c=campaign();sent=[]
def unsubscribe_second(email,*_):
 sent.append(email);other=S2 if email.startswith(S1) else S1;execute('update newsletter_subscriptions set unsubscribed_at=now() where id=%s',(other,));return True
worker(c,unsubscribe_second);assert len(sent)==1;assert execute('select sent_count from newsletter_campaigns where id=%s',(c['id'],))==1
execute('update newsletter_subscriptions set unsubscribed_at=null where campus_id=%s',(C,));c=campaign();sent=[]
def cancel_after_first(email,*_):sent.append(email);db.rpc('hg_cancel_newsletter_campaign',{'p_actor':A,'p_campaign':c['id'],'p_scope':C});return True
worker(c,cancel_after_first);assert len(sent)==1;assert execute('select status from newsletter_campaigns where id=%s',(c['id'],))=='cancelled'
# Provider ambiguity never becomes an automatic resend or confirmed rejection.
c=campaign();attempts=[]
def timeout(email,*_):attempts.append(email);raise TimeoutError('Controlled provider response loss')
worker(c,timeout);assert len(attempts)==2;worker(c,lambda *args:(_ for _ in ()).throw(AssertionError('Retried uncertain send')));assert execute('select failed_count from newsletter_campaigns where id=%s',(c['id'],))==0;assert execute("select count(*) from newsletter_deliveries where campaign_id=%s and status='uncertain'",(c['id'],))==2
# Process exits after committed handoff: saved receipt is classified, never resent.
c=campaign();code="""import os,psycopg2
x=psycopg2.connect(os.environ['EVENT_RELIABILITY_TEST_DSN']);x.autocommit=True;q=x.cursor();q.execute(\"select set_config('request.jwt.claims','{\\\"role\\\":\\\"service_role\\\"}',false)\");q.execute('select hg_claim_newsletter_delivery(%s,%s,%s)',(os.environ['NEWS_TEST_CAMPAIGN'],os.environ['NEWS_TEST_SUB'],os.environ['NEWS_TEST_SUB']+'@example.invalid'));print('HANDOFF_COMMITTED',flush=True);input()
"""
child=subprocess.Popen([sys.executable,'-c',code],env=dict(os.environ,NEWS_TEST_CAMPAIGN=c['id'],NEWS_TEST_SUB=S1),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:assert child.stdout.readline().strip()=='HANDOFF_COMMITTED';child.kill();child.wait(timeout=5)
finally:
 if child.poll() is None:child.kill();child.wait(timeout=5)
execute("update newsletter_deliveries set created_at=now()-interval '20 minutes' where campaign_id=%s",(c['id'],));sent=[];worker(c,lambda email,*args:(sent.append(email) or True));assert sent==[S2+'@example.invalid'];assert execute('select status from newsletter_campaigns where id=%s',(c['id'],))=='partial'
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:db.rpc('hg_refresh_newsletter_summary',{'p_campaign':c['id'],'p_uncertain_notice':'Controlled unknown'}),range(4)))
assert all(r['sent']==1 and r['uncertain']==1 and r['failed']==0 for r in results),results
c=campaign()
with ThreadPoolExecutor(max_workers=4) as pool:claims=list(pool.map(lambda _:db.rpc('hg_claim_newsletter_delivery',{'p_campaign':c['id'],'p_subscription':S1,'p_email':S1+'@example.invalid'}),range(4)))
assert sum(1 for claim in claims if claim and claim.get('id'))==1,claims
print('PASS real worker/PostgreSQL: unsubscribe and cancel between recipients, provider timeout, committed handoff process exit, and concurrent receipt-derived totals')
