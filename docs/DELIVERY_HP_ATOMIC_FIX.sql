-- Replace the old signature, rather than leaving an overlapping overload.
-- Defaults preserve five-argument callers while updated callers pass the
-- expected multiplier and complete squad award for atomic validation/storage.
BEGIN;
DROP FUNCTION public.hg_credit_delivery_hp_atomic(uuid,uuid,integer,text,text);
CREATE FUNCTION public.hg_credit_delivery_hp_atomic(
  p_order_id uuid,p_user_id uuid,p_hp_amount integer,
  p_tier_name text DEFAULT NULL,p_source_type text DEFAULT 'food_order',
  p_expected_multiplier numeric DEFAULT NULL,p_total_hp_amount integer DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $delivery$
DECLARE
  v_order public.orders%ROWTYPE;
  v_profile public.profiles%ROWTYPE;
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
    UPDATE public.profiles SET next_order_hp_multiplier=1 WHERE id=p_user_id;
  END IF;
  UPDATE public.orders SET hp_earned=v_total_hp,hp_credited_at=now(),updated_at=now()
    WHERE id=p_order_id RETURNING * INTO v_order;
  RETURN jsonb_build_object('success',true,'order_id',p_order_id,'hp_earned',v_total_hp,
    'owner_hp',v_owner_hp,'multiplier_applied',v_multiplier,'hp_credited_at',v_order.hp_credited_at);
END
$delivery$;
REVOKE ALL ON FUNCTION public.hg_credit_delivery_hp_atomic(uuid,uuid,integer,text,text,numeric,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_credit_delivery_hp_atomic(uuid,uuid,integer,text,text,numeric,integer)
  TO service_role;
COMMIT;
