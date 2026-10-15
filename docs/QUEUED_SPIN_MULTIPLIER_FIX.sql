-- Preserve separate multiplier wins using the existing pending receipt queue.
CREATE OR REPLACE FUNCTION public.hg_spin_exclusive_atomic(p_user_id uuid, p_intent_key uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
  INSERT INTO public.exclusive_spin_fulfillments(id,user_id,prize_name,status,campus_id,intent_key,created_at)
    VALUES(v_receipt_id,p_user_id,v_prize.name,'pending',v_profile.campus_id,p_intent_key,clock_timestamp());
  UPDATE public.exclusive_spins SET spin_count=spin_count-1 WHERE id=v_credit.id;
  v_result:=jsonb_build_object('prize',v_prize.name,'prize_id',v_prize.id,'prize_type',v_kind,
    'reward_config',v_prize.reward_config,'fulfillment_id',v_receipt_id,
    'fulfillment_status',CASE WHEN v_kind IN ('physical','free_delivery','hp_multiplier') THEN 'pending' ELSE 'fulfilled' END,
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
    -- This receipt queues the credit; every win retains its own cap.
    v_result:=v_result||jsonb_build_object('delivery_cap',(v_prize.reward_config->>'cap')::numeric);
  ELSIF v_kind='hp_multiplier' THEN
    -- One pending immutable receipt per win. The legacy scalar remains a
    -- separate earlier entitlement and is consumed before this new queue.
    v_result:=v_result||jsonb_build_object('hp_multiplier',(v_prize.reward_config->>'multiplier')::numeric,'queued',true);
  ELSIF v_kind<>'physical' THEN RAISE EXCEPTION 'spin_reward_config_invalid';
  END IF;
  SELECT COALESCE(sum(spin_count),0) INTO v_remaining FROM public.exclusive_spins
    WHERE user_id=p_user_id AND campus_id=v_profile.campus_id AND spin_count>0
      AND expires_at>=now() AND source IN ('leaderboard_prize','tier_grant','admin_grant');
  v_result:=v_result||jsonb_build_object('spins_remaining',v_remaining);
  UPDATE public.exclusive_spin_fulfillments SET result_snapshot=v_result,
    status=CASE WHEN v_kind IN ('physical','free_delivery','hp_multiplier') THEN 'pending' ELSE 'fulfilled' END,
    fulfilled_at=CASE WHEN v_kind IN ('physical','free_delivery','hp_multiplier') THEN NULL ELSE now() END WHERE id=v_receipt_id;
  RETURN v_result;
END
$function$
;
CREATE OR REPLACE FUNCTION public.hg_credit_delivery_hp_atomic(p_order_id uuid, p_user_id uuid, p_hp_amount integer, p_tier_name text DEFAULT NULL::text, p_source_type text DEFAULT 'food_order'::text, p_expected_multiplier numeric DEFAULT NULL::numeric, p_total_hp_amount integer DEFAULT NULL::integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_profile public.profiles%ROWTYPE;
  v_receipt public.exclusive_spin_fulfillments%ROWTYPE;
  v_multiplier numeric;
  v_owner_hp integer;
  v_total_hp integer;
  v_txn_id uuid;
BEGIN
  SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('error','order_not_found'); END IF;
  IF v_order.user_id IS DISTINCT FROM p_user_id OR p_user_id IS NULL THEN
    RETURN jsonb_build_object('error','order_user_mismatch');
  END IF;
  IF v_order.hp_credited_at IS NOT NULL THEN
    RETURN jsonb_build_object('already_credited',true,'hp_earned',v_order.hp_earned,
      'hp_credited_at',v_order.hp_credited_at);
  END IF;
  IF v_order.status::text<>'delivered' OR v_order.payment_status::text<>'paid' THEN
    RETURN jsonb_build_object('error','paid_delivery_required');
  END IF;
  IF p_hp_amount IS NULL OR p_hp_amount<0 OR p_total_hp_amount<0
    OR (p_total_hp_amount IS NOT NULL AND p_total_hp_amount<p_hp_amount)
    OR (p_expected_multiplier IS NOT NULL AND (p_expected_multiplier<1
      OR p_expected_multiplier::text IN ('NaN','Infinity','-Infinity'))) THEN
    RETURN jsonb_build_object('error','invalid_award');
  END IF;
  SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id FOR UPDATE;
  IF NOT FOUND OR NOT v_profile.is_active THEN RETURN jsonb_build_object('error','user_inactive'); END IF;
  v_multiplier:=greatest(COALESCE(v_profile.next_order_hp_multiplier,1),1);
  IF v_multiplier=1 THEN
    SELECT * INTO v_receipt FROM public.exclusive_spin_fulfillments
      WHERE user_id=p_user_id AND (campus_id=v_order.campus_id OR campus_id IS NULL)
        AND status='pending' AND applied_order_id IS NULL AND result_snapshot->>'prize_type'='hp_multiplier'
      ORDER BY created_at,id LIMIT 1 FOR UPDATE;
    IF FOUND THEN
      v_multiplier:=(v_receipt.result_snapshot->'reward_config'->>'multiplier')::numeric;
      IF v_multiplier IS NULL OR v_multiplier NOT BETWEEN 1.01 AND 10 OR v_multiplier::text IN ('NaN','Infinity','-Infinity') THEN
        RAISE EXCEPTION 'spin_multiplier_receipt_invalid';
      END IF;
    END IF;
  END IF;
  IF p_expected_multiplier IS NOT NULL AND v_multiplier<>p_expected_multiplier THEN
    RETURN jsonb_build_object('error','multiplier_changed');
  END IF;
  v_owner_hp:=p_hp_amount;
  v_total_hp:=COALESCE(p_total_hp_amount,p_hp_amount);
  IF v_owner_hp>0 THEN
    v_txn_id:=public.hg_add_hp_transaction(p_user_id,'earn',v_owner_hp,p_source_type,'order',
      p_order_id,NULL,jsonb_build_object('source','hg_credit_delivery_hp_atomic','tier',p_tier_name,
      'hp_calculated_by','python','multiplier',v_multiplier,'total_award',v_total_hp),
      now()+interval '12 months',v_order.campus_id);
    IF v_txn_id IS NULL THEN RAISE EXCEPTION 'delivery_hp_award_failed'; END IF;
    PERFORM public.increment_monthly_hp_tracker(p_user_id,
      to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),v_owner_hp);
  END IF;
  -- A zero-food reward-only delivery does not consume a food-earning perk.
  IF v_multiplier>1 AND v_total_hp>0 THEN
    IF v_receipt.id IS NOT NULL THEN
      UPDATE public.exclusive_spin_fulfillments SET status='fulfilled',applied_order_id=p_order_id,fulfilled_at=now()
        WHERE id=v_receipt.id;
    ELSE
      UPDATE public.profiles SET next_order_hp_multiplier=1 WHERE id=p_user_id;
    END IF;
  END IF;
  UPDATE public.orders SET hp_earned=v_total_hp,hp_credited_at=now(),updated_at=now()
    WHERE id=p_order_id RETURNING * INTO v_order;
  RETURN jsonb_build_object('success',true,'order_id',p_order_id,'hp_earned',v_total_hp,
    'owner_hp',v_owner_hp,'multiplier_applied',v_multiplier,'hp_credited_at',v_order.hp_credited_at);
END
$function$
;
REVOKE ALL ON FUNCTION public.hg_spin_exclusive_atomic(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_spin_exclusive_atomic(uuid,uuid) TO service_role;
REVOKE ALL ON FUNCTION public.hg_credit_delivery_hp_atomic(uuid,uuid,integer,text,text,numeric,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_credit_delivery_hp_atomic(uuid,uuid,integer,text,text,numeric,integer) TO service_role;
