"""Disposable local Docker database only; never runs against customer accounts."""
import concurrent.futures, json, subprocess, uuid
CONTAINER='hg-wallet-transfer-test'
def sql(statement,check=True):
 p=subprocess.run(['docker','exec','-i',CONTAINER,'psql','-U','postgres','-XAt','-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True)
 if check and p.returncode:raise AssertionError(p.stderr)
 return p
c,a,b=[str(uuid.uuid4()) for _ in range(3)]
code=b.replace('-','').upper()
created=[]
def send(transfer,actor=a,recipient=b,amount=10000):
 payload=json.dumps({'recipient_id':recipient,'recipient_code':recipient.replace('-',''),'amount_kobo':amount})
 return sql(f"SET statement_timeout='15s';SELECT hg_wallet_transfer('send','{actor}','{transfer}','{payload}');",False)
def parallel(tasks):
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:return list(executor.map(lambda args:send(*args),tasks))
def balances():return [float(x) for x in sql(f"SELECT balance FROM wallets WHERE user_id IN ('{a}','{b}') ORDER BY user_id").stdout.splitlines()]
def reset(amount=1000,daily=1000000):
 sql(f"DELETE FROM hg_internal.wallet_transfers WHERE campus_id='{c}';DELETE FROM wallet_transactions WHERE campus_id='{c}';UPDATE wallets SET balance={amount} WHERE user_id IN ('{a}','{b}');DELETE FROM system_settings WHERE campus_id='{c}';INSERT INTO system_settings(key,value,campus_id) VALUES('wallet_transfer_daily_limit','{daily}','{c}');")
try:
 sql(f"INSERT INTO campuses(id,name,slug) VALUES('{c}','Local concurrency','local-{c}');INSERT INTO auth.users(id,email) VALUES('{a}','local-{a}@example.invalid'),('{b}','local-{b}@example.invalid');UPDATE profiles SET campus_id='{c}',is_active=true,referral_code=upper(replace(id::text,'-','')) WHERE id IN ('{a}','{b}');INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES('wallet_transfer',true,'{c}');INSERT INTO wallets(user_id,balance,campus_id) VALUES('{a}',1000,'{c}'),('{b}',1000,'{c}');")
 t=str(uuid.uuid4());results=parallel([(t,)]*16)
 assert all(p.returncode==0 for p in results),[p.stderr for p in results if p.returncode]
 assert sql(f"SELECT count(*) FROM wallet_transactions WHERE reference_id='{t}'").stdout.strip()=='2'
 assert sum(balances())==2000 and min(balances())==900
 print('PASS: sixteen identical requests create one paired transfer')
 reset(amount=100)
 results=parallel([(str(uuid.uuid4()),a,b,10000) for _ in range(12)])
 assert sum(p.returncode==0 for p in results)==1,[p.stderr for p in results]
 assert sorted(balances())==[0,200]
 print('PASS: simultaneous competing sends cannot overdraw')
 reset(daily=500)
 results=parallel([(str(uuid.uuid4()),a,b,10000) for _ in range(12)])
 assert sum(p.returncode==0 for p in results)==5
 assert sorted(balances())==[500,1500]
 print('PASS: simultaneous sends share one daily allowance')
 reset()
 results=parallel([(str(uuid.uuid4()),*( (a,b) if i%2 else (b,a)),1000) for i in range(20)])
 assert all(p.returncode==0 for p in results),[p.stderr for p in results if p.returncode]
 assert balances()==[1000,1000]
 print('PASS: opposing transfers conserve balances without deadlock')
finally:
 sql(f"DELETE FROM hg_internal.wallet_transfers WHERE campus_id='{c}';DELETE FROM wallet_transactions WHERE campus_id='{c}';DELETE FROM wallets WHERE user_id IN ('{a}','{b}');DELETE FROM profiles WHERE id IN ('{a}','{b}');DELETE FROM auth.users WHERE id IN ('{a}','{b}');DELETE FROM system_settings WHERE campus_id='{c}';DELETE FROM feature_flags WHERE campus_id='{c}';DELETE FROM campuses WHERE id='{c}';")
