-- Preserve the old helper name for its existing trigger/RPC dependencies.
CREATE OR REPLACE FUNCTION public.hg_set_profile_tier_from_balance(p_user_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person public.profiles%rowtype;earned bigint;r jsonb;
BEGIN
 SELECT * INTO person FROM public.profiles WHERE id=p_user_id FOR UPDATE;
 IF person.id IS NULL OR person.is_active IS NOT TRUE OR person.role::text<>'student' OR person.campus_id IS NULL THEN RETURN person.current_tier_id;END IF;
 SELECT coalesce(sum(amount),0) INTO earned FROM public.hp_transactions WHERE user_id=p_user_id AND campus_id=person.campus_id AND type='earn' AND status='active' AND created_at>=now()-interval '120 days';
 UPDATE public.profiles SET hp_earned_120day=earned WHERE id=p_user_id AND hp_earned_120day IS DISTINCT FROM earned;
 r:=public.hg_recalculate_tier_atomic(p_user_id);
 RETURN (r->'tier'->>'id')::uuid;
END$$;
REVOKE ALL ON FUNCTION public.hg_set_profile_tier_from_balance(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_set_profile_tier_from_balance(uuid) TO service_role;
-- Reconciliation already calls the helper for insert/update/delete. Retain the
-- activity timestamp trigger, without a second identical tier/ledger scan.
DO $$DECLARE definition text;needle text:='  PERFORM public.hg_set_profile_tier_from_balance(NEW.user_id);';BEGIN
 definition:=pg_get_functiondef('public.hg_on_hp_transaction_insert()'::regprocedure);
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected HP activity trigger';END IF;
 EXECUTE replace(definition,needle,'  -- Tier update is owned by hg_on_hp_transaction_reconcile.');
END$$;
