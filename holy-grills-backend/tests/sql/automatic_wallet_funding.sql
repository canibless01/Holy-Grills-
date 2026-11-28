-- Isolated random identities, no provider requests, no retained fixtures.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE uid uuid:=gen_random_uuid(); other_uid uuid:=gen_random_uuid(); pid uuid:=gen_random_uuid();
 new_id uuid; terms jsonb; result jsonb; dispatch jsonb; history jsonb; reference text; other_ref text; n integer;
 auth jsonb:='{"authorization_code":"test-only-private","reusable":true,"channel":"card","last4":"4081","brand":"visa"}';
BEGIN
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES
  (uid,'audit-auto-funding-'||uid||'@example.invalid','{"full_name":"Audit rollback funding"}'),
  (other_uid,'audit-auto-funding-'||other_uid||'@example.invalid','{"full_name":"Audit rollback other"}');
 INSERT INTO public.wallets(user_id,balance) VALUES(uid,0),(other_uid,0) ON CONFLICT(user_id) DO UPDATE SET balance=0;
 terms:=jsonb_build_object('amount_kobo',20000,'interval_days',2,'stop_after',3,'consent_version','wallet-auto-funding-v2');
 result:=public.hg_wallet_auto_funding('create',uid,pid,terms);
 reference:=result->'plan'->>'setup_reference';
 IF NOT (result->>'created')::boolean THEN RAISE EXCEPTION 'plan not created'; END IF;
 result:=public.hg_wallet_auto_funding('create',uid,pid,terms);
 IF (result->>'created')::boolean THEN RAISE EXCEPTION 'intent replay created another plan'; END IF;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('create',uid,pid,terms||'{"amount_kobo":30000}');
  RAISE EXCEPTION 'changed intent accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='changed intent accepted' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('create',uid,gen_random_uuid(),terms);
  RAISE EXCEPTION 'duplicate open plan accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='duplicate open plan accepted' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('stop',other_uid,pid);
  RAISE EXCEPTION 'foreign stop accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='foreign stop accepted' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('confirm',uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',19999,'requested_amount_kobo',20000,'fees_kobo',305));
  RAISE EXCEPTION 'underpayment accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='underpayment accepted' THEN RAISE; END IF; END;
 IF (SELECT balance FROM public.wallets WHERE user_id=uid)<>0 THEN RAISE EXCEPTION 'unpaid plan credited'; END IF;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('confirm',uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',19999,'fees_kobo',305));
  RAISE EXCEPTION 'wrong requested contribution accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='wrong requested contribution accepted' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('confirm',uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',35001,'requested_amount_kobo',20000));
  RAISE EXCEPTION 'out-of-buffer unknown fee accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='out-of-buffer unknown fee accepted' THEN RAISE; END IF; END;
 IF (SELECT balance FROM public.wallets WHERE user_id=uid)<>0 THEN RAISE EXCEPTION 'invalid fee breakdown credited'; END IF;
 result:=public.hg_wallet_auto_funding('confirm',uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 IF result->'plan'->>'state'<>'active' OR (result->'plan'->>'successful_payments')::integer<>1 OR (SELECT balance FROM public.wallets WHERE user_id=uid)<>200 THEN RAISE EXCEPTION 'first payment failed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.wallet_transactions WHERE provider_reference=reference AND amount=200
   AND (metadata->>'fees_kobo')::integer=305) THEN RAISE EXCEPTION 'gross fee leaked into wallet credit'; END IF;
 PERFORM public.hg_wallet_auto_funding('confirm',uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 IF (SELECT balance FROM public.wallets WHERE user_id=uid)<>200 OR (SELECT count(*) FROM public.wallet_transactions WHERE provider_reference=reference)<>1 THEN RAISE EXCEPTION 'callback/webhook duplicate credit'; END IF;
 IF EXISTS(SELECT 1 FROM public.wallet_transactions WHERE provider_reference=reference AND metadata::text LIKE '%test-only-private%') THEN RAISE EXCEPTION 'credential leaked to public ledger'; END IF;
 BEGIN
  PERFORM public.hg_wallet_auto_funding('confirm',other_uid,pid,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305));
  RAISE EXCEPTION 'foreign confirmation accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 UPDATE hg_internal.wallet_funding_plans SET next_due_at=now()-interval '7 days' WHERE id=pid;
 dispatch:=public.hg_wallet_auto_funding('dispatch',NULL,pid);
 other_ref:=dispatch->>'reference';
 IF dispatch->>'authorization_email' NOT LIKE 'audit-auto-funding-%' OR other_ref IS NULL THEN RAISE EXCEPTION 'due dispatch missing'; END IF;
 IF public.hg_wallet_auto_funding('dispatch',NULL,pid)<>'{}'::jsonb THEN RAISE EXCEPTION 'uncertain charge dispatched twice'; END IF;
 result:=public.hg_wallet_auto_funding('stop',uid,pid);
 IF NOT (result->>'in_flight')::boolean OR result->'card_authorization' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'stop did not revoke future authority'; END IF;
 -- A later authorization debit uses the same bounded fallback when fees are omitted.
 PERFORM public.hg_wallet_auto_funding('confirm',NULL,NULL,jsonb_build_object('reference',other_ref,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000));
 IF (SELECT balance FROM public.wallets WHERE user_id=uid)<>400 OR (SELECT state FROM hg_internal.wallet_funding_plans WHERE id=pid)<>'stopped' THEN RAISE EXCEPTION 'late paid debit lost or reactivated stopped plan'; END IF;
 IF public.hg_wallet_auto_funding('dispatch',NULL,pid)<>'{}'::jsonb THEN RAISE EXCEPTION 'stopped plan charged'; END IF;

 -- Count completion, non-reusable card, and late first payment after cancellation.
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms||'{"stop_after":1}');reference:=result->'plan'->>'setup_reference';
 result:=public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 IF result->'plan'->>'state'<>'completed' OR result->'plan'->'card_authorization' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'automatic count stop failed'; END IF;
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms);reference:=result->'plan'->>'setup_reference';
 result:=public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization','{}'::jsonb));
 IF result->'plan'->>'state'<>'attention' THEN RAISE EXCEPTION 'non-reusable card activated'; END IF;
 PERFORM public.hg_wallet_auto_funding('stop',uid,new_id);
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms);reference:=result->'plan'->>'setup_reference';
 PERFORM public.hg_wallet_auto_funding('stop',uid,new_id);
 result:=public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 IF result->'plan'->>'state'<>'stopped' THEN RAISE EXCEPTION 'cancelled checkout reactivated'; END IF;

 -- Failure cannot advance the cadence; late money remains creditable once.
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms);reference:=result->'plan'->>'setup_reference';
 PERFORM public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 UPDATE hg_internal.wallet_funding_plans SET next_due_at=now()-interval '1 second' WHERE id=new_id;
 dispatch:=public.hg_wallet_auto_funding('dispatch',NULL,new_id);reference:=dispatch->>'reference';
 PERFORM public.hg_wallet_auto_funding('failed',NULL,NULL,jsonb_build_object('reference',reference));
 IF (SELECT state FROM hg_internal.wallet_funding_plans WHERE id=new_id)<>'attention' OR public.hg_wallet_auto_funding('dispatch',NULL,new_id)<>'{}'::jsonb THEN RAISE EXCEPTION 'failed debit kept charging'; END IF;
 PERFORM public.hg_wallet_auto_funding('stop',uid,new_id);
 -- An initialization timeout must not strand a later verified first payment.
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms);reference:=result->'plan'->>'setup_reference';
 PERFORM public.hg_wallet_auto_funding('setup_failed',uid,new_id);
 result:=public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 IF result->'plan'->>'state'<>'active' OR result->'plan'->'last_issue' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'verified setup recovery stayed paused'; END IF;
 PERFORM public.hg_wallet_auto_funding('stop',uid,new_id);
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms||jsonb_build_object('stop_after',NULL,'end_at',now()+interval '3 days'));reference:=result->'plan'->>'setup_reference';
 PERFORM public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 UPDATE hg_internal.wallet_funding_plans SET end_at=now()-interval '1 second',next_due_at=now()-interval '1 day' WHERE id=new_id;
 IF public.hg_wallet_auto_funding('dispatch',NULL,new_id)<>'{}'::jsonb THEN RAISE EXCEPTION 'expired plan dispatched'; END IF;
 PERFORM public.hg_wallet_auto_funding('due',NULL,NULL,'{"limit":20}');
 IF (SELECT state FROM hg_internal.wallet_funding_plans WHERE id=new_id)<>'completed' THEN RAISE EXCEPTION 'end date not completed'; END IF;
 new_id:=gen_random_uuid();
 result:=public.hg_wallet_auto_funding('create',uid,new_id,terms);reference:=result->'plan'->>'setup_reference';
 PERFORM public.hg_wallet_auto_funding('confirm',uid,new_id,jsonb_build_object('reference',reference,'currency','NGN','amount_kobo',20305,'requested_amount_kobo',20000,'fees_kobo',305,'authorization',auth));
 UPDATE hg_internal.wallet_funding_plans SET next_due_at=now()-interval '1 day' WHERE id=new_id;
 UPDATE public.profiles SET is_active=false WHERE id=uid;
 result:=public.hg_wallet_auto_funding('dispatch',NULL,new_id);
 IF result<>'{}'::jsonb OR (SELECT state FROM hg_internal.wallet_funding_plans WHERE id=new_id)<>'attention' THEN RAISE EXCEPTION 'inactive member charged'; END IF;
 result:=public.hg_wallet_funding_attention('claim',NULL,20);
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(result) x WHERE x->>'id'=new_id::text) THEN RAISE EXCEPTION 'paused plan notice missing'; END IF;
 PERFORM public.hg_wallet_funding_attention('done',new_id);
 UPDATE hg_internal.wallet_funding_plans SET attention_next_at=now()-interval '1 second' WHERE id=new_id;
 result:=public.hg_wallet_funding_attention('claim',NULL,20);
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(result) x WHERE x->>'id'=new_id::text) THEN RAISE EXCEPTION 'paused notice replayed'; END IF;
 history:=public.hg_wallet_auto_funding('list',uid);
 IF jsonb_array_length(history)<8 OR EXISTS(SELECT 1 FROM jsonb_array_elements(history) h WHERE h->'attempts' IS NULL OR jsonb_typeof(h->'attempts')<>'array') THEN RAISE EXCEPTION 'complete plan/contribution history missing'; END IF;
 IF has_function_privilege('anon','public.hg_wallet_auto_funding(text,uuid,uuid,jsonb)','execute')
 OR has_function_privilege('authenticated','public.hg_wallet_auto_funding(text,uuid,uuid,jsonb)','execute')
 OR has_table_privilege('authenticated','hg_internal.wallet_funding_plans','SELECT') THEN RAISE EXCEPTION 'funding credentials reachable by client'; END IF;
 SELECT count(*) INTO n FROM public.wallet_transactions WHERE user_id=uid AND type='credit';
 IF (SELECT balance FROM public.wallets WHERE user_id=uid)<>n*200 THEN RAISE EXCEPTION 'cash conservation failed'; END IF;
 RAISE NOTICE 'PASS: consent, ownership, exact credits, replay, dispatch/stop, late webhooks, limits, failure, inactive member and private credentials';
END $audit$;
ROLLBACK;
