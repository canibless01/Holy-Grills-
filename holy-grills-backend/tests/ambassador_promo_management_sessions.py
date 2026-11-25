"""Concurrent SQL proof; refuses any remote or non-test DSN."""
import os,threading,uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
DSN=os.environ.get('HG_PROMO_TEST_DSN','host=127.0.0.1 port=55449 dbname=engagement user=postgres password=engagement-local')
p=parse_dsn(DSN)
if p.get('host') not in ('127.0.0.1','localhost') or p.get('dbname')!='engagement':
    raise SystemExit('Only a localhost engagement test database is allowed')
def sql(statement,args=(),one=False):
    with psycopg2.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout='8s'; SET lock_timeout='6s'")
            cursor.execute(statement,args)
            if cursor.description:return cursor.fetchone()[0] if one else cursor.fetchall()
def race(calls):
    gate=threading.Barrier(len(calls))
    def worker(call):gate.wait(timeout=10);return sql(*call,one=True)
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(worker,calls))
uid=lambda:str(uuid.uuid4())
c,manager,student=uid(),uid(),uid()
try:
    sql("INSERT INTO campuses(id,name,slug,is_active) VALUES(%s,'Local promo race',%s,true)",(c,'local-'+c))
    for identity,role in [(manager,'community_manager'),(student,'student')]:
        sql('INSERT INTO auth.users(id,email) VALUES(%s,%s)',(identity,identity+'@example.invalid'))
        sql('INSERT INTO profiles(id,email,full_name,role,campus_id,is_active) VALUES(%s,%s,%s,%s,%s,true) ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,is_active=true',(identity,identity+'@example.invalid','Local test',role,c))
    sql("INSERT INTO ambassadors(profile_id,campus_id,status) VALUES(%s,%s,'active')",(student,c))
    call="SELECT hg_create_ambassador_promo_atomic(%s,%s,%s,'Race {{link}}',null,'2026-11',true,'{}')"
    results=race([(call,(manager,uid(),c)) for _ in range(6)])
    ids={r['message']['id'] for r in results};assert len(ids)==1,results
    mid=ids.pop();assert sql('SELECT count(*) FROM ambassador_promo_assignments WHERE message_id=%s',(mid,),True)==1
    print('PASS six concurrent requests with different UUIDs produce one message and one assignment',flush=True)
    edit="SELECT hg_manage_ambassador_promo(%s,%s,1,'edit',jsonb_build_object('caption',%s))"
    results=race([(edit,(manager,mid,'Edit one {{link}}')),(edit,(manager,mid,'Edit two {{link}}'))])
    assert sum('message' in r for r in results)==1 and sum(r.get('error')=='promo_stale' for r in results)==1,results
    assert sql('SELECT count(*) FROM ambassador_promo_history WHERE message_id=%s',(mid,),True)==1
    print('PASS concurrent edits preserve one winner and return a stale-version conflict to the other',flush=True)
    results=race([("SELECT hg_manage_ambassador_promo(%s,%s,2,'delete')",(manager,mid)) for _ in range(4)])
    assert all(r.get('message',{}).get('deleted_at') for r in results),results
    assert sql('SELECT count(*) FROM ambassador_promo_history WHERE message_id=%s',(mid,),True)==2
    assert sql(call,(manager,uid(),c),True).get('error')=='promo_deleted'
    print('PASS four concurrent deletes keep one deletion history and the original create receipt cannot resurrect it',flush=True)
finally:
    # Identifiers belong to this isolated localhost database and this run only.
    sql('DELETE FROM ambassador_promo_history WHERE message_id IN (SELECT id FROM ambassador_promo_messages WHERE campus_id=%s)',(c,))
    sql('DELETE FROM ambassador_promo_assignments WHERE ambassador_id=%s',(student,))
    sql('DELETE FROM ambassador_promo_messages WHERE campus_id=%s',(c,))
    sql('DELETE FROM ambassadors WHERE profile_id=%s',(student,))
    sql('DELETE FROM profiles WHERE id IN (%s,%s)',(manager,student))
    sql('DELETE FROM auth.users WHERE id IN (%s,%s)',(manager,student))
    sql('DELETE FROM campuses WHERE id=%s',(c,))
