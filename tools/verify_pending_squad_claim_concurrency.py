"""Run against a disposable local metadata database, never production.

Usage: TEST_SQUAD_DATABASE_URL=postgresql://... python tools/verify_pending_squad_claim_concurrency.py
Real production rollback/RLS proof lives in tests/sql/pending_squad_claim_recovery_rollback.sql.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import psycopg2

url = os.environ['TEST_SQUAD_DATABASE_URL']
assert urlparse(url).hostname in ('127.0.0.1', 'localhost'), 'Disposable local database only'
ids = [str(uuid.uuid4()) for _ in range(6)]
campus, user, owner, order, pending, second = ids


def connect():
    connection = psycopg2.connect(url)
    connection.autocommit = True
    return connection


def claim(row=pending):
    with psycopg2.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='10s'")
            cursor.execute("SELECT set_config('request.jwt.claims', %s, true)", ('{"role":"service_role"}',))
            cursor.execute('SELECT hg_claim_pending_squad_hp(%s,%s)', (row, user))
            return cursor.fetchone()[0]


connection = connect()
q = connection.cursor()
try:
    q.execute('INSERT INTO campuses(id,name,slug) VALUES(%s,%s,%s)', (campus, 'Local squad concurrency', 'local-'+campus))
    for actor in (user, owner):
        q.execute("INSERT INTO profiles(id,email,campus_id,is_active,hp_balance,push_enabled) VALUES(%s,%s,%s,true,0,true)", (actor, actor+'@example.invalid', campus))
    q.execute("INSERT INTO orders(id,user_id,campus_id,status,payment_status,is_squad_order,squad_hp_distributed) VALUES(%s,%s,%s,'delivered','paid',true,true)", (order, owner, campus))
    for row in (pending, second):
        q.execute("INSERT INTO pending_squad_hp(id,email,order_id,campus_id,hp_amount,status) VALUES(%s,%s,%s,%s,25,'pending')", (row, user+'@example.invalid', order, campus))
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(claim, [pending, second]*12))
    assert all(r.get('success') for r in replies), replies
    assert sum(r.get('awarded', 0) for r in replies) == 25
    q.execute('SELECT hp_balance FROM profiles WHERE id=%s', (user,)); assert q.fetchone()[0] == 25
    q.execute('SELECT count(*) FROM hp_transactions WHERE user_id=%s AND reference_id=%s', (user, order)); assert q.fetchone()[0] == 1
    q.execute('SELECT sum(total_earned) FROM monthly_hp_tracker WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 25
    q.execute('SELECT count(*) FROM notifications WHERE user_id=%s AND reference_id=%s', (user, order)); assert q.fetchone()[0] == 2
    q.execute('SELECT count(*) FROM notification_deliveries WHERE user_id=%s', (user,)); assert q.fetchone()[0] == 1
    print('PASS: 24 concurrent signup/sweep requests, including duplicate pending rows, yield one HP grant, one monthly increment and one inbox/push pair')
finally:
    for table in ('notification_deliveries', 'notifications', 'hp_transactions', 'monthly_hp_tracker'):
        q.execute('DELETE FROM '+table+' WHERE user_id=%s', (user,))
    q.execute('DELETE FROM pending_squad_hp WHERE order_id=%s', (order,))
    q.execute('DELETE FROM hg_internal.delivery_subsidy_movements WHERE order_id=%s', (order,))
    q.execute('DELETE FROM hg_internal.delivery_subsidy_ledger WHERE order_id=%s', (order,))
    q.execute('DELETE FROM orders WHERE id=%s', (order,))
    q.execute('DELETE FROM profiles WHERE id=ANY(%s::uuid[])', ([user, owner],))
    q.execute('DELETE FROM campuses WHERE id=%s', (campus,))
    connection.close()
