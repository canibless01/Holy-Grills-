"""Disposable localhost-only concurrency proof for membership milestone rewards."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import psycopg2

url = os.environ['TEST_MEMBERSHIP_DATABASE_URL']
assert urlparse(url).hostname in ('127.0.0.1', 'localhost'), 'Local fixtures only'
campus, user, config = [str(uuid.uuid4()) for _ in range(3)]
connection = psycopg2.connect(url); connection.autocommit = True
q = connection.cursor()


def award(_):
    with psycopg2.connect(url) as worker:
        with worker.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='10s'")
            cursor.execute("SELECT set_config('request.jwt.claims', %s, true)", ('{"role":"service_role"}',))
            cursor.execute('SELECT hg_award_membership_anniversary(%s)', (user,))
            return cursor.fetchone()[0]


try:
    q.execute('SELECT coalesce(max(months),0)+120 FROM membership_rewards'); milestone = q.fetchone()[0]
    q.execute('INSERT INTO campuses(id,name,slug,is_active) VALUES(%s,%s,%s,true)', (campus, 'Local membership concurrency', 'local-'+campus))
    q.execute("INSERT INTO profiles(id,email,campus_id,is_active,role,hp_balance,push_enabled,created_at) VALUES(%s,%s,%s,true,'student',0,true,((now() AT TIME ZONE 'Africa/Lagos')::date-make_interval(months=>%s))::date::timestamp AT TIME ZONE 'Africa/Lagos')", (user, user+'@example.invalid', campus, milestone))
    q.execute('INSERT INTO membership_rewards(id,months,hp_awarded,is_active,campus_id) VALUES(%s,%s,70,true,%s)', (config, milestone, campus))
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(award, range(24)))
    assert all(r.get('success') for r in replies), replies
    assert sum(r.get('awarded', 0) for r in replies) == 70
    q.execute('UPDATE membership_rewards SET hp_awarded=999 WHERE id=%s', (config,))
    replay = award(0); assert replay['hp'] == 70 and replay['awarded'] == 0
    q.execute('SELECT hp_balance FROM profiles WHERE id=%s', (user,)); assert q.fetchone()[0] == 70
    q.execute('SELECT count(*) FROM hp_transactions WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 1
    q.execute('SELECT sum(total_earned) FROM monthly_hp_tracker WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 70
    q.execute('SELECT count(*) FROM notifications WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 2
    q.execute('SELECT count(*) FROM notification_deliveries WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 1
    print('PASS: 24 concurrent milestone claims and changed-setting replay yield one original 70 HP award, one monthly increment and one inbox/push pair')
finally:
    for table in ('notification_deliveries', 'notifications', 'hp_transactions', 'monthly_hp_tracker'):
        q.execute('DELETE FROM '+table+' WHERE user_id=%s', (user,))
    q.execute('DELETE FROM membership_rewards WHERE id=%s', (config,))
    q.execute('DELETE FROM profiles WHERE id=%s', (user,))
    q.execute('DELETE FROM campuses WHERE id=%s', (campus,))
    connection.close()
