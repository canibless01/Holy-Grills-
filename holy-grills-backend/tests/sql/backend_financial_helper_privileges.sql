BEGIN;
DO $audit$
DECLARE command text;
BEGIN
 PERFORM set_config('request.jwt.claims','{"role":"authenticated","sub":"00000000-0000-4000-8000-000000000001"}',true);
 PERFORM set_config('role','authenticated',true);
 FOREACH command IN ARRAY ARRAY[
  'SELECT public.hg_transfer_hp_atomic(NULL,NULL,1,NULL,NULL)',
  'SELECT public.hg_redeem_reward(NULL,NULL)',
  'SELECT public.hg_redeem_flash_reward_atomic(NULL,NULL)',
  'SELECT public.hg_reserve_order_refund(NULL,1)'
 ] LOOP
  BEGIN
   EXECUTE command;
   RAISE EXCEPTION 'direct financial helper unexpectedly allowed';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
 END LOOP;
 PERFORM set_config('role','none',true);
 IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname IN ('hg_transfer_hp_atomic','hg_redeem_reward','hg_redeem_flash_reward_atomic','hg_reserve_order_refund')
 AND (has_function_privilege('anon',p.oid,'EXECUTE') OR has_function_privilege('authenticated',p.oid,'EXECUTE') OR NOT has_function_privilege('service_role',p.oid,'EXECUTE'))) THEN RAISE EXCEPTION 'financial helper grants mismatch'; END IF;
END $audit$;
ROLLBACK;
SELECT 'Direct authenticated calls denied; existing helpers service-only; no data changes' AS evidence;
