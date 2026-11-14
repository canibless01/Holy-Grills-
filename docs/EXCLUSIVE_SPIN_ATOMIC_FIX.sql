-- Persist typed prize configuration and immutable spin receipts in existing
-- prize/fulfilment tables. A spin's credit, prize, HP and receipt commit together.
BEGIN;
ALTER TABLE public.exclusive_spin_prizes
  ADD COLUMN reward_config jsonb NOT NULL DEFAULT '{"kind":"physical"}'::jsonb;
ALTER TABLE public.exclusive_spin_fulfillments
  ADD COLUMN intent_key uuid,
  ADD COLUMN result_snapshot jsonb;
ALTER TABLE public.exclusive_spins ADD COLUMN grant_snapshot jsonb;

-- Preserve established global rewards while removing runtime name dispatch.
UPDATE public.exclusive_spin_prizes SET reward_config=jsonb_build_object('kind','hp','amount',300)
  WHERE name='+300 HP';
UPDATE public.exclusive_spin_prizes SET reward_config=jsonb_build_object('kind','hp','amount',750)
  WHERE name='+750 HP';
UPDATE public.exclusive_spin_prizes SET reward_config=jsonb_build_object('kind','free_delivery','cap',
  COALESCE((SELECT value::text::numeric FROM public.system_settings
    WHERE key='exclusive_spin_free_delivery_cap' AND campus_id IS NULL),1500))
  WHERE name='Free Delivery';

ALTER TABLE public.exclusive_spin_prizes ADD CONSTRAINT exclusive_spin_reward_config_valid CHECK (
  jsonb_typeof(reward_config)='object' AND CASE reward_config->>'kind'
    WHEN 'physical' THEN true
    WHEN 'hp' THEN jsonb_typeof(reward_config->'amount')='number'
      AND (reward_config->>'amount')::numeric BETWEEN 1 AND 100000
      AND (reward_config->>'amount')::numeric=trunc((reward_config->>'amount')::numeric)
    WHEN 'free_delivery' THEN jsonb_typeof(reward_config->'cap')='number'
      AND (reward_config->>'cap')::numeric BETWEEN 1 AND 100000
    WHEN 'hp_multiplier' THEN jsonb_typeof(reward_config->'multiplier')='number'
      AND (reward_config->>'multiplier')::numeric BETWEEN 1.01 AND 10
    ELSE false END IS TRUE
);
CREATE UNIQUE INDEX exclusive_spin_fulfillments_intent_key_idx
  ON public.exclusive_spin_fulfillments(user_id,intent_key) WHERE intent_key IS NOT NULL;

-- Public clients cannot forge receipts or mint/replenish credits. Existing
-- staff fulfilment routes only need these three update columns.
REVOKE ALL ON public.exclusive_spins FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.exclusive_spins TO authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.exclusive_spins TO service_role;
REVOKE ALL ON public.exclusive_spin_fulfillments FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.exclusive_spin_fulfillments TO authenticated;
GRANT UPDATE(status,fulfilled_by,fulfilled_at) ON public.exclusive_spin_fulfillments TO authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.exclusive_spin_fulfillments TO service_role;
REVOKE ALL ON public.exclusive_spin_prizes FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.exclusive_spin_prizes TO authenticated,service_role;
DROP POLICY IF EXISTS "exclusive_spin_prizes: authenticated read active" ON public.exclusive_spin_prizes;
CREATE POLICY "exclusive_spin_prizes: authenticated read active"
  ON public.exclusive_spin_prizes FOR SELECT TO authenticated
  USING (is_active AND (campus_id IS NULL OR campus_id=public.hg_user_campus_id()
    OR public.hg_is_campus_admin(campus_id)));

CREATE OR REPLACE FUNCTION public.hg_spin_exclusive_atomic(p_user_id uuid,p_intent_key uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $spin$
DECLARE
  v_profile public.profiles%ROWTYPE;
  v_credit public.exclusive_spins%ROWTYPE;
  v_prize public.exclusive_spin_prizes%ROWTYPE;
  v_receipt public.exclusive_spin_fulfillments%ROWTYPE;
  v_result jsonb; v_hp jsonb; v_kind text; v_amount integer;
  v_total numeric; v_pick numeric; v_cursor numeric := 0;
  v_campus_pool boolean; v_remaining integer; v_receipt_id uuid := gen_random_uuid();
  v_multiplier numeric := 1; v_raw jsonb; v_scope uuid; v_expiry text;
BEGIN
  IF p_user_id IS NULL OR p_intent_key IS NULL THEN
    RETURN jsonb_build_object('error','invalid_intent');
  END IF;
  -- A single per-user lock covers independent intents and response-loss replays.
  SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id FOR UPDATE;
  IF NOT FOUND OR NOT v_profile.is_active THEN
    RETURN jsonb_build_object('error','user_inactive');
  END IF;
  SELECT * INTO v_receipt FROM public.exclusive_spin_fulfillments
    WHERE user_id=p_user_id AND intent_key=p_intent_key;
  IF FOUND THEN RETURN v_receipt.result_snapshot || jsonb_build_object('idempotent',true); END IF;
  IF NOT EXISTS(SELECT 1 FROM public.feature_flags
    WHERE feature_name='exclusive_spin' AND campus_id IS NULL AND is_active) THEN
    RETURN jsonb_build_object('error','feature_disabled');
  END IF;
  IF v_profile.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses
    WHERE id=v_profile.campus_id AND is_active) THEN
    RETURN jsonb_build_object('error','campus_required');
  END IF;
  SELECT * INTO v_credit FROM public.exclusive_spins
    WHERE user_id=p_user_id AND campus_id=v_profile.campus_id AND spin_count>0
      AND expires_at>=now() AND source IN ('leaderboard_prize','tier_grant','admin_grant')
    ORDER BY expires_at,id LIMIT 1 FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('error','no_credits'); END IF;

  SELECT EXISTS(SELECT 1 FROM public.exclusive_spin_prizes WHERE is_active
    AND weight>0 AND campus_id=v_profile.campus_id) INTO v_campus_pool;
  SELECT sum(weight) INTO v_total FROM public.exclusive_spin_prizes WHERE is_active AND weight>0
    AND (CASE WHEN v_campus_pool THEN campus_id=v_profile.campus_id ELSE campus_id IS NULL END);
  IF COALESCE(v_total,0)<=0 THEN RETURN jsonb_build_object('error','pool_unavailable'); END IF;
  v_pick := random()*v_total;
  FOR v_prize IN SELECT * FROM public.exclusive_spin_prizes WHERE is_active AND weight>0
    AND (CASE WHEN v_campus_pool THEN campus_id=v_profile.campus_id ELSE campus_id IS NULL END)
    ORDER BY id FOR SHARE
  LOOP
    v_cursor:=v_cursor+v_prize.weight;
    EXIT WHEN v_pick<v_cursor;
  END LOOP;
  IF v_prize.id IS NULL OR v_pick>=v_cursor THEN
    RETURN jsonb_build_object('error','pool_unavailable');
  END IF;
  v_kind:=v_prize.reward_config->>'kind';
  -- Snapshot is the award's contract, so later edits cannot change a won prize.
  INSERT INTO public.exclusive_spin_fulfillments(id,user_id,prize_name,status,campus_id,intent_key)
    VALUES(v_receipt_id,p_user_id,v_prize.name,'pending',v_profile.campus_id,p_intent_key);
  UPDATE public.exclusive_spins SET spin_count=spin_count-1 WHERE id=v_credit.id;
  v_result:=jsonb_build_object('prize',v_prize.name,'prize_id',v_prize.id,'prize_type',v_kind,
    'reward_config',v_prize.reward_config,'fulfillment_id',v_receipt_id,
    'fulfillment_status',CASE WHEN v_kind='physical' THEN 'pending' ELSE 'fulfilled' END,
    'idempotent',false);
  IF v_kind='hp' THEN
    -- Match the existing active-HP event multiplier contract and scope/expiry.
    IF EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name='hp_multiplier'
      AND campus_id IS NULL AND is_active) THEN
      SELECT value,campus_id INTO v_raw,v_scope FROM public.system_settings
        WHERE key='hp_multiplier' AND (campus_id=v_profile.campus_id OR campus_id IS NULL)
        ORDER BY campus_id NULLS LAST LIMIT 1;
      BEGIN
        IF (v_raw#>>'{}')::numeric IN (0.5,1,2) THEN v_multiplier:=(v_raw#>>'{}')::numeric; END IF;
        SELECT value#>>'{}' INTO v_expiry FROM public.system_settings
          WHERE key='multiplier_expires_at' AND campus_id IS NOT DISTINCT FROM v_scope;
        IF NULLIF(v_expiry,'')::timestamptz<now() THEN v_multiplier:=1; END IF;
      EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format THEN v_multiplier:=1;
      END;
    END IF;
    -- Existing award_active_hp only scales earning multipliers above one.
    v_amount:=round((v_prize.reward_config->>'amount')::numeric*greatest(v_multiplier,1));
    v_hp:=public.record_hp_transaction_atomic(p_user_id,v_amount,'earn','active','exclusive_spin',
      'exclusive_spin',v_receipt_id,NULL,'Exclusive spin: '||v_prize.name,v_profile.campus_id);
    IF NOT COALESCE((v_hp->>'success')::boolean,false) THEN
      RAISE EXCEPTION 'spin_hp_award_failed' USING ERRCODE='P0001';
    END IF;
    PERFORM public.increment_monthly_hp_tracker(p_user_id,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),v_amount);
    v_result:=v_result||jsonb_build_object('hp_won',v_amount);
  ELSIF v_kind='free_delivery' THEN
    UPDATE public.profiles SET next_order_free_delivery_cap=greatest(
      COALESCE(next_order_free_delivery_cap,0),(v_prize.reward_config->>'cap')::numeric) WHERE id=p_user_id;
    v_result:=v_result||jsonb_build_object('delivery_cap',(v_prize.reward_config->>'cap')::numeric);
  ELSIF v_kind='hp_multiplier' THEN
    UPDATE public.profiles SET next_order_hp_multiplier=greatest(
      COALESCE(next_order_hp_multiplier,1),(v_prize.reward_config->>'multiplier')::numeric) WHERE id=p_user_id;
    v_result:=v_result||jsonb_build_object('hp_multiplier',(v_prize.reward_config->>'multiplier')::numeric);
  ELSIF v_kind<>'physical' THEN RAISE EXCEPTION 'spin_reward_config_invalid';
  END IF;
  SELECT COALESCE(sum(spin_count),0) INTO v_remaining FROM public.exclusive_spins
    WHERE user_id=p_user_id AND campus_id=v_profile.campus_id AND spin_count>0
      AND expires_at>=now() AND source IN ('leaderboard_prize','tier_grant','admin_grant');
  v_result:=v_result||jsonb_build_object('spins_remaining',v_remaining);
  UPDATE public.exclusive_spin_fulfillments SET result_snapshot=v_result,
    status=CASE WHEN v_kind='physical' THEN 'pending' ELSE 'fulfilled' END,
    fulfilled_at=CASE WHEN v_kind='physical' THEN NULL ELSE now() END WHERE id=v_receipt_id;
  RETURN v_result;
END
$spin$;
REVOKE ALL ON FUNCTION public.hg_spin_exclusive_atomic(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_spin_exclusive_atomic(uuid,uuid) TO service_role;

-- Credit grants use their existing primary key as the request identity. The
-- saved original grant remains recoverable even after its credits are spent.
CREATE OR REPLACE FUNCTION public.hg_grant_exclusive_spins_atomic(
  p_actor_id uuid,p_user_id uuid,p_intent_key uuid,p_spins integer,p_validity_days integer,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $grant$
DECLARE v_actor public.profiles%ROWTYPE;v_user public.profiles%ROWTYPE;
  v_existing public.exclusive_spins%ROWTYPE;v_expires timestamptz;v_snapshot jsonb;
BEGIN
  IF p_intent_key IS NULL OR p_spins NOT BETWEEN 1 AND 10
    OR p_validity_days NOT BETWEEN 1 AND 365 OR p_spins IS NULL OR p_validity_days IS NULL
    OR length(COALESCE(p_reason,''))>200 THEN RETURN jsonb_build_object('error','invalid_grant'); END IF;
  SELECT * INTO v_actor FROM public.profiles WHERE id=p_actor_id AND is_active;
  IF NOT FOUND OR v_actor.role NOT IN ('admin','super_admin') THEN
    RETURN jsonb_build_object('error','forbidden');
  END IF;
  SELECT * INTO v_user FROM public.profiles WHERE id=p_user_id FOR UPDATE;
  IF NOT FOUND OR NOT v_user.is_active OR v_user.campus_id IS NULL THEN
    RETURN jsonb_build_object('error','target_unavailable');
  END IF;
  IF v_actor.role<>'super_admin' AND v_actor.campus_id IS DISTINCT FROM v_user.campus_id THEN
    RETURN jsonb_build_object('error','forbidden');
  END IF;
  SELECT * INTO v_existing FROM public.exclusive_spins WHERE id=p_intent_key;
  IF FOUND THEN
    IF v_existing.user_id IS DISTINCT FROM p_user_id
      OR v_existing.grant_snapshot->>'actor_id' IS DISTINCT FROM p_actor_id::text
      OR (v_existing.grant_snapshot->>'spins')::integer IS DISTINCT FROM p_spins
      OR (v_existing.grant_snapshot->>'validity_days')::integer IS DISTINCT FROM p_validity_days
      OR v_existing.grant_snapshot->>'reason' IS DISTINCT FROM COALESCE(p_reason,'') THEN
      RETURN jsonb_build_object('error','intent_conflict');
    END IF;
    RETURN jsonb_build_object('spin_id',v_existing.id,'user_id',p_user_id,'spins',p_spins,
      'expires_at',v_existing.expires_at,'idempotent',true);
  END IF;
  v_expires:=now()+make_interval(days=>p_validity_days);
  v_snapshot:=jsonb_build_object('actor_id',p_actor_id,'spins',p_spins,
    'validity_days',p_validity_days,'reason',COALESCE(p_reason,''));
  INSERT INTO public.exclusive_spins(id,user_id,spin_count,source,month,expires_at,campus_id,grant_snapshot)
    VALUES(p_intent_key,p_user_id,p_spins,'admin_grant',to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),
      v_expires,v_user.campus_id,v_snapshot);
  RETURN jsonb_build_object('spin_id',p_intent_key,'user_id',p_user_id,'spins',p_spins,
    'expires_at',v_expires,'idempotent',false);
END
$grant$;
REVOKE ALL ON FUNCTION public.hg_grant_exclusive_spins_atomic(uuid,uuid,uuid,integer,integer,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_grant_exclusive_spins_atomic(uuid,uuid,uuid,integer,integer,text) TO service_role;
COMMIT;
