-- Trigger execution uses the already-attached trigger, not a client RPC grant.
-- Retain public RLS predicates: only RETURNS trigger helpers are restricted.
DO $$ DECLARE signature regprocedure;BEGIN
 FOREACH signature IN ARRAY ARRAY[
 'public.hg_guard_order_review_insert()'::regprocedure,
 'public.hg_guard_share_event_insert()'::regprocedure,
 'public.hg_guard_squad_member_insert()'::regprocedure,
 'public.hg_protect_leaderboard_reward_columns()'::regprocedure,
 'public.hg_protect_notification_columns()'::regprocedure,
 'public.hg_protect_order_review_columns()'::regprocedure,
 'public.hg_protect_squad_member_columns()'::regprocedure] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=signature AND prorettype='trigger'::regtype) THEN RAISE EXCEPTION 'Expected a trigger helper: %',signature;END IF;
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon, authenticated',signature);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',signature);
 END LOOP;
END $$;
