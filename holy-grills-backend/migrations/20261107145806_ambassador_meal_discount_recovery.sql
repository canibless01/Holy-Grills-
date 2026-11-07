-- Lock only the selected benefit. Cancellation must not revive a voided promise.
CREATE OR REPLACE FUNCTION public.hg_redeem_ambassador_meal_discount(
  p_discount_id uuid,
  p_order_id uuid,
  p_ambassador_id uuid,
  p_amount numeric,
  p_meal_item_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE
  v_discount public.ambassador_meal_discounts;
  v_redemption_id uuid;
BEGIN

  SELECT * INTO v_discount
  FROM public.ambassador_meal_discounts
  WHERE id = p_discount_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'meal_discount_not_found' USING ERRCODE = 'P0002';
  END IF;
  IF v_discount.ambassador_id <> p_ambassador_id THEN
    RAISE EXCEPTION 'meal_discount_wrong_owner' USING ERRCODE = '42501';
  END IF;
  IF v_discount.status = 'voided' THEN
    RAISE EXCEPTION 'meal_discount_voided' USING ERRCODE = '23514';
  END IF;
  IF v_discount.status = 'expired' OR v_discount.expires_at <= now() THEN
    RAISE EXCEPTION 'meal_discount_expired' USING ERRCODE = '23514';
  END IF;
  IF v_discount.uses_remaining <= 0 OR v_discount.status <> 'active' THEN
    RAISE EXCEPTION 'meal_discount_no_uses_left' USING ERRCODE = '23514';
  END IF;
  IF p_amount IS NULL OR p_amount::text IN ('NaN','Infinity','-Infinity')
     OR p_amount <= 0 OR p_amount > v_discount.max_meal_value THEN
    RAISE EXCEPTION 'meal_discount_amount_invalid' USING ERRCODE = '23514';
  END IF;
  IF EXISTS (SELECT 1 FROM public.ambassador_meal_discount_redemptions WHERE order_id = p_order_id) THEN
    RAISE EXCEPTION 'meal_discount_order_already_redeemed' USING ERRCODE = '23505';
  END IF;

  INSERT INTO public.ambassador_meal_discount_redemptions
    (discount_id, order_id, ambassador_id, meal_item_id, amount)
  VALUES
    (p_discount_id, p_order_id, p_ambassador_id, p_meal_item_id, p_amount)
  RETURNING id INTO v_redemption_id;

  UPDATE public.ambassador_meal_discounts
  SET uses_remaining = uses_remaining - 1,
      status = CASE WHEN uses_remaining - 1 = 0 THEN 'redeemed' ELSE status END
  WHERE id = p_discount_id
  RETURNING * INTO v_discount;

  RETURN jsonb_build_object(
    'redemption_id', v_redemption_id,
    'discount_id', p_discount_id,
    'code', v_discount.code,
    'amount', p_amount,
    'uses_remaining', v_discount.uses_remaining
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_redeem_ambassador_meal_discount(uuid, uuid, uuid, numeric, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_redeem_ambassador_meal_discount(uuid, uuid, uuid, numeric, uuid)
  TO service_role;


CREATE OR REPLACE FUNCTION public.hg_restore_ambassador_meal_discount(p_order_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE
  v_redemption public.ambassador_meal_discount_redemptions;
BEGIN
  SELECT * INTO v_redemption
  FROM public.ambassador_meal_discount_redemptions
  WHERE order_id = p_order_id AND restored_at IS NULL
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('restored', false);
  END IF;

  UPDATE public.ambassador_meal_discount_redemptions
  SET restored_at = now()
  WHERE id = v_redemption.id;

  UPDATE public.ambassador_meal_discounts
  SET uses_remaining = LEAST(uses_total, uses_remaining + 1),
      status = CASE WHEN status = 'voided' THEN 'voided'
                    WHEN expires_at <= now() THEN 'expired' ELSE 'active' END
  WHERE id = v_redemption.discount_id;

  RETURN jsonb_build_object(
    'restored', true,
    'discount_id', v_redemption.discount_id,
    'amount', v_redemption.amount
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_restore_ambassador_meal_discount(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_restore_ambassador_meal_discount(uuid) TO service_role;
