"""Parallel SQL acceptance against the disposable local Docker DB only.

Requires hg-auto-funding-test with the migration and local fixture schema.
No network provider calls, production connection option, or production data.
"""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

USER, PLAN = str(uuid4()), str(uuid4())


def sql(query):
    result = subprocess.run(['docker', 'exec', '-i', 'hg-auto-funding-test', 'psql', '-U', 'postgres', '-Atq', '-v', 'ON_ERROR_STOP=1'],
                            input=query, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def rpc(action, user=None, plan=None, data=None):
    payload = json.dumps(data or {}).replace("'", "''")
    query = f"SELECT public.hg_wallet_auto_funding('{action}',{repr(user) if user else 'NULL'},{repr(plan) if plan else 'NULL'},'{payload}'::jsonb);"
    return json.loads(sql(query))


try:
    sql(f"INSERT INTO auth.users(id,email) VALUES('{USER}','local-concurrency-{USER}@example.invalid'); INSERT INTO wallets(user_id,balance) VALUES('{USER}',0);")
    terms = {'amount_kobo': 20000, 'interval_days': 2, 'stop_after': 3, 'consent_version': 'wallet-auto-funding-v1'}
    with ThreadPoolExecutor(max_workers=12) as pool:
        created = list(pool.map(lambda _: rpc('create', USER, PLAN, terms), range(24)))
    assert sum(row['created'] for row in created) == 1
    reference = created[0]['plan']['setup_reference']
    payment = {'reference': reference, 'currency': 'NGN', 'amount_kobo': 20000,
               'authorization': {'authorization_code': 'test-only-private', 'reusable': True, 'channel': 'card', 'brand': 'visa', 'last4': '4081'}}
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda _: rpc('confirm', USER, PLAN, payment), range(36)))
    assert sql(f"SELECT balance FROM wallets WHERE user_id='{USER}';") == '200.0000000000000000'
    assert sql(f"SELECT count(*) FROM wallet_transactions WHERE user_id='{USER}';") == '1'
    sql(f"UPDATE hg_internal.wallet_funding_plans SET next_due_at=now()-interval '1 day' WHERE id='{PLAN}';")
    with ThreadPoolExecutor(max_workers=12) as pool:
        dispatched = list(pool.map(lambda _: rpc('dispatch', plan=PLAN), range(24)))
    assert sum(bool(row) for row in dispatched) == 1
    reference2 = next(row['reference'] for row in dispatched if row)
    with ThreadPoolExecutor(max_workers=12) as pool:
        # Stop and success callbacks contend on the same plan lock.
        futures = [pool.submit(rpc, 'stop', USER, PLAN) for _ in range(12)]
        futures += [pool.submit(rpc, 'confirm', data={'reference': reference2, 'currency': 'NGN', 'amount_kobo': 20000}) for _ in range(24)]
        for future in futures: future.result()
    assert float(sql(f"SELECT balance FROM wallets WHERE user_id='{USER}';")) == 400
    assert sql(f"SELECT count(*) FROM wallet_transactions WHERE user_id='{USER}';") == '2'
    assert rpc('dispatch', plan=PLAN) == {}
    assert rpc('get', USER, PLAN)['state'] == 'stopped'
    print(json.dumps({'passed': True, 'parallel_intents': 24, 'parallel_first_confirmations': 36, 'parallel_dispatch_claims': 24,
                      'parallel_stop_callbacks': 36, 'credits': 2, 'balance_naira': 400, 'provider_posts': 0, 'production_writes': 0}))
finally:
    sql(f"DELETE FROM hg_internal.wallet_funding_attempts WHERE plan_id='{PLAN}'; DELETE FROM hg_internal.wallet_funding_plans WHERE id='{PLAN}'; DELETE FROM wallet_transactions WHERE user_id='{USER}'; DELETE FROM wallets WHERE user_id='{USER}'; DELETE FROM profiles WHERE id='{USER}'; DELETE FROM auth.users WHERE id='{USER}';")
