"""Disposable localhost-only tier transition race proof; no external delivery."""
import os,uuid
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from pathlib import Path
url=os.environ['TEST_TIER_DATABASE_URL'];assert urlparse(url).hostname in ('127.0.0.1','localhost')
c,u,base,mid=[str(uuid.uuid4()) for _ in range(4)]
conn=psycopg2.connect(url);conn.autocommit=True;q=conn.cursor()

def transition(mode):
    with psycopg2.connect(url) as db:
        with db.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='10s'")
            cursor.execute("SELECT set_config('request.jwt.claims', %s, true)",('{"role":"service_role"}',))
            cursor.execute('SELECT hg_recalculate_tier_atomic(%s,%s,7)',(u,mode));return cursor.fetchone()[0]

def parallel(mode):
    with ThreadPoolExecutor(max_workers=8) as pool:return list(pool.map(transition,[mode]*24))

try:
    q.execute(Path('holy-grills-backend/migrations/20261113090155_atomic_tier_and_grace_transitions.sql').read_text().replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION'))
    q.execute('ALTER TABLE user_tiers ALTER COLUMN id SET DEFAULT gen_random_uuid()')
    q.execute('INSERT INTO campuses(id,name,slug,is_active) VALUES(%s,%s,%s,true)',(c,'Local tier concurrency','local-'+c))
    for tid,name,points,maintenance,rank in [(base,'Base',0,0,0),(mid,'Mid',100,70,1)]:
        q.execute('INSERT INTO hp_tiers(id,name,slug,min_points,maintenance_points,sort_order,campus_id,is_active) VALUES(%s,%s,%s,%s,%s,%s,%s,true)',(tid,name+' '+c,'local-'+tid,points,maintenance,rank,c))
    q.execute("INSERT INTO profiles(id,email,role,is_active,campus_id,current_tier_id,hp_earned_120day,hp_balance,push_enabled,email_notifications) VALUES(%s,%s,'student',true,%s,%s,120,0,true,true)",(u,u+'@example.invalid',c,base))
    parallel('upgrade')
    q.execute('SELECT count(*) FROM user_tiers WHERE user_id=%s',(u,));assert q.fetchone()[0]==1
    q.execute('UPDATE profiles SET hp_earned_120day=0 WHERE id=%s',(u,));parallel('grace')
    q.execute("SELECT count(*) FROM user_tiers WHERE user_id=%s AND event='grace'",(u,));assert q.fetchone()[0]==1
    q.execute("UPDATE profiles SET tier_grace_ends_at=now()-interval '1 second' WHERE id=%s",(u,));parallel('grace')
    q.execute('SELECT current_tier_id::text,hp_balance,tier_grace_ends_at FROM profiles WHERE id=%s',(u,));assert q.fetchone()==(base,0,None)
    for table,count in [('user_tiers',3),('notifications',9),('notification_deliveries',6)]:
        q.execute('SELECT count(*) FROM '+table+' WHERE user_id=%s',(u,));assert q.fetchone()[0]==count,table
    print('PASS: 24 concurrent upgrades, grace starts and expired-grace transitions each create one state/history/notice set, with no HP mutation')
finally:
    for table in ('notification_deliveries','notifications','user_tiers'):
        q.execute('DELETE FROM '+table+' WHERE user_id=%s',(u,))
    q.execute('DELETE FROM profiles WHERE id=%s',(u,));q.execute('DELETE FROM hp_tiers WHERE campus_id=%s',(c,));q.execute('DELETE FROM campuses WHERE id=%s',(c,));conn.close()
