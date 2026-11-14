-- Transactional acceptance: all fixture users, balances and receipts roll back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE TEMP TABLE transfer_test_actors(sender uuid, recipient uuid, transfer uuid, fresh_recipient uuid);
GRANT SELECT ON transfer_test_actors TO service_role;
CREATE FUNCTION pg_temp.check_transfer(ok boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Transfer check failed: %',label; END IF; END $$;
CREATE FUNCTION pg_temp.transfer_error(statement text, expected text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 BEGIN EXECUTE statement; EXCEPTION WHEN OTHERS THEN
  IF SQLERRM=expected THEN RETURN; END IF;
  RAISE EXCEPTION 'Expected %, got %',expected,SQLERRM;
 END;
 RAISE EXCEPTION 'Expected failure: %',expected;
END $$;
DO $test$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid();
 a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); outsider uuid:=gen_random_uuid(); empty_user uuid:=gen_random_uuid();
 transfer uuid:=gen_random_uuid(); fresh uuid; p jsonb; result jsonb; before_hp numeric; before_count bigint; before_balance numeric; u uuid;
BEGIN
 INSERT INTO transfer_test_actors VALUES(a,b,transfer,empty_user);
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Wallet transfers','audit-wallet-'||c),(other_c,'[AUDIT rollback] Other wallet','audit-wallet-'||other_c);
 FOREACH u IN ARRAY ARRAY[a,b,outsider,empty_user] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-wallet-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Wallet member"}');
  UPDATE public.profiles SET campus_id=CASE WHEN u=outsider THEN other_c ELSE c END,is_active=true,referral_code=upper(replace(u::text,'-','')) WHERE id=u;
 END LOOP;
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('wallet_transfer',true,c);
 INSERT INTO public.system_settings(key,value,campus_id) VALUES('wallet_transfer_min_amount','1',c),('wallet_transfer_max_amount','500',c),('wallet_transfer_daily_limit','500',c);
 INSERT INTO public.wallets(user_id,balance,currency,campus_id) VALUES(a,1000,'NGN',c),(b,100,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,currency='NGN';
 SELECT hp_balance INTO before_hp FROM public.profiles WHERE id=a;
 result:=public.hg_wallet_transfer('lookup',a,NULL,jsonb_build_object('code',lower(replace(b::text,'-',''))));
 PERFORM pg_temp.check_transfer(result->>'id'=b::text AND NOT result ? 'email' AND NOT result ? 'balance','same-campus private lookup');
 result:=public.hg_wallet_transfer('lookup',a,NULL,jsonb_build_object('lookup_type','email','value',' AUDIT-WALLET-'||b||'@EXAMPLE.INVALID '));
 PERFORM pg_temp.check_transfer(result->>'id'=b::text,'exact email lookup ignores case and outside whitespace');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('code',replace(outsider::text,'-',''))),'recipient_unavailable');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('code',replace(a::text,'-',''))),'self_transfer');
 UPDATE profiles SET is_active=false WHERE id=b;
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('code',replace(b::text,'-',''))),'recipient_unavailable');
 UPDATE profiles SET is_active=true WHERE id=b;
 p:=jsonb_build_object('recipient_id',b,'recipient_code',replace(b::text,'-',''),'amount_kobo',25025,'note','Dinner together');
 result:=public.hg_wallet_transfer('send',a,transfer,p);
 PERFORM pg_temp.check_transfer((result->>'amount')::numeric=250.25 AND result->>'replayed'='false' AND (result->>'fee')::numeric=0,'completed receipt');
 PERFORM pg_temp.check_transfer((SELECT balance=749.75 FROM wallets WHERE user_id=a) AND (SELECT balance=350.25 FROM wallets WHERE user_id=b),'paired balances');
 PERFORM pg_temp.check_transfer((SELECT sum(balance)=1100 FROM wallets WHERE user_id IN(a,b)),'conservation');
 PERFORM pg_temp.check_transfer((SELECT count(*)=2 AND sum(CASE WHEN type='credit' THEN amount ELSE -amount END)=0 FROM wallet_transactions WHERE reference_type='wallet_transfer' AND reference_id=transfer),'paired ledger');
 PERFORM pg_temp.check_transfer((SELECT wallet_balance=749.75 AND hp_balance IS NOT DISTINCT FROM before_hp FROM profiles WHERE id=a),'profile mirror/no HP');
 result:=public.hg_wallet_transfer('send',a,transfer,p);
 PERFORM pg_temp.check_transfer(result->>'replayed'='true' AND (SELECT count(*)=2 FROM wallet_transactions WHERE reference_id=transfer),'idempotent retry');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,transfer,p||'{"amount_kobo":25026}'),'transfer_intent_conflict');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',outsider,transfer,p),'transfer_not_found');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''get'',%L,%L)',outsider,transfer),'transfer_not_found');
 result:=public.hg_wallet_transfer('get',b,transfer);
 PERFORM pg_temp.check_transfer(result->>'direction'='received' AND (result->>'balance_after')::numeric=350.25 AND NOT result ? 'sender_balance_after','owned recipient receipt');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p||'{"amount_kobo":50100}'),'transfer_amount_out_of_range');
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p||'{"amount_kobo":25000}'),'transfer_daily_limit');
 UPDATE wallets SET balance=1 WHERE user_id=a;
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p||'{"amount_kobo":200}'),'insufficient_wallet_balance');
 UPDATE wallets SET balance=749.75 WHERE user_id=a;
 UPDATE wallets SET currency='USD' WHERE user_id=b;
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p||'{"amount_kobo":100}'),'wallet_unavailable');
 UPDATE wallets SET currency='NGN' WHERE user_id=b;
 -- Error during recipient credit must roll back the earlier source debit.
 SELECT balance INTO before_balance FROM wallets WHERE user_id=a;
 SELECT count(*) INTO before_count FROM wallet_transactions WHERE user_id=a;
 BEGIN
  -- A temporary trigger simulates an interrupted second half on any numeric precision.
  EXECUTE 'CREATE FUNCTION pg_temp.fail_transfer_credit() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN IF NEW.balance>OLD.balance THEN RAISE EXCEPTION ''simulated_credit_failure''; END IF;RETURN NEW;END $f$';
  EXECUTE format('CREATE TRIGGER audit_fail_credit BEFORE UPDATE ON public.wallets FOR EACH ROW WHEN (NEW.user_id=%L::uuid) EXECUTE FUNCTION pg_temp.fail_transfer_credit()',b);
  PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p||'{"amount_kobo":100}'),'simulated_credit_failure');
  DROP TRIGGER audit_fail_credit ON public.wallets;
 END;
 PERFORM pg_temp.check_transfer((SELECT balance=before_balance FROM wallets WHERE user_id=a) AND (SELECT count(*)=before_count FROM wallet_transactions WHERE user_id=a),'failed credit rolls back debit and ledger');
 fresh:=gen_random_uuid();
 result:=public.hg_wallet_transfer('send',a,fresh,jsonb_build_object('recipient_id',empty_user,'recipient_code',replace(empty_user::text,'-',''),'amount_kobo',100));
 PERFORM pg_temp.check_transfer((SELECT balance=1 FROM wallets WHERE user_id=empty_user),'missing wallet created atomically');
 UPDATE feature_flags SET is_active=false WHERE campus_id=c AND feature_name='wallet_transfer';
 PERFORM pg_temp.transfer_error(format('SELECT hg_wallet_transfer(''send'',%L,%L,%L)',a,gen_random_uuid(),p),'transfers_paused');
 UPDATE profiles SET campus_id=other_c WHERE id=b;
 result:=public.hg_wallet_transfer('send',a,transfer,p);
 PERFORM pg_temp.check_transfer(result->>'replayed'='true','completed replay survives campus/flag changes');
 PERFORM pg_temp.check_transfer(public.hg_wallet_transfer('notice',NULL,transfer)->>'id'=transfer::text,'notification lookup');
 PERFORM public.hg_wallet_transfer('notified',NULL,transfer);
 PERFORM pg_temp.check_transfer(public.hg_wallet_transfer('notice',NULL,transfer) IS NULL,'notification completion');
 result:=public.hg_wallet_transfer('due',NULL,NULL,'{"limit":20}');
 PERFORM pg_temp.check_transfer(EXISTS(SELECT 1 FROM jsonb_array_elements(result) x WHERE x->>'id'=fresh::text),'notification recovery lease');
 result:=public.hg_wallet_transfer('due',NULL,NULL,'{"limit":20}');
 PERFORM pg_temp.check_transfer(NOT EXISTS(SELECT 1 FROM jsonb_array_elements(result) x WHERE x->>'id'=fresh::text),'lease prevents duplicate recovery');
 PERFORM pg_temp.check_transfer(NOT has_function_privilege('anon','public.hg_wallet_transfer(text,uuid,uuid,jsonb)','EXECUTE') AND NOT has_function_privilege('authenticated','public.hg_wallet_transfer_receipt(uuid,uuid)','EXECUTE'),'RPC service only');
 PERFORM pg_temp.check_transfer(NOT has_table_privilege('authenticated','hg_internal.wallet_transfers','SELECT'),'private receipts');
END $test$;
-- Verify the actual backend role, not just the schema owner's permissions.
SET LOCAL ROLE service_role;
DO $role$ DECLARE actor record; value jsonb; BEGIN
 SELECT * INTO actor FROM transfer_test_actors;
 value:=public.hg_wallet_transfer('get',actor.sender,actor.transfer);
 PERFORM pg_temp.check_transfer(value->>'id'=actor.transfer::text,'service-role receipt access');
 value:=public.hg_wallet_transfer('limits',actor.sender);
 PERFORM pg_temp.check_transfer(value->>'enabled'='false','service-role configured limits');
 value:=public.hg_wallet_transfer('due',NULL,NULL,'{"limit":0}');
 PERFORM pg_temp.check_transfer(value='[]'::jsonb,'service-role private outbox access');
END $role$;
RESET ROLE;
UPDATE public.feature_flags SET is_active=true WHERE feature_name='wallet_transfer' AND campus_id IN
 (SELECT p.campus_id FROM public.profiles p JOIN transfer_test_actors a ON a.sender=p.id);
SET LOCAL ROLE service_role;
DO $write$ DECLARE actor record; value jsonb; BEGIN
 SELECT * INTO actor FROM transfer_test_actors;
 value:=public.hg_wallet_transfer('send',actor.sender,gen_random_uuid(),jsonb_build_object('recipient_id',actor.fresh_recipient,'recipient_code',replace(actor.fresh_recipient::text,'-',''),'amount_kobo',100));
 PERFORM pg_temp.check_transfer(value->>'status'='completed','service-role atomic wallet write');
END $write$;
RESET ROLE;
ROLLBACK;
