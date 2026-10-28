-- ============================================================================
-- Campus Ambassador Programme — 3/4 — reward RPCs (meal discounts)
-- ----------------------------------------------------------------------------
-- Meal discounts are their own bucket (code, max meal value, uses, expiry) —
-- the wallet, HP and free-side services are reused unchanged for the other
-- reward categories. service_role only; Flask performs the financial-admin
-- role check, validation and audit logging before calling these.
-- ============================================================================

-- Deferred cross-table foreign keys (both tables now exist).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_amb_grants_meal_discount') THEN
    ALTER TABLE public.ambassador_grants
      ADD CONSTRAINT fk_amb_grants_meal_discount
      FOREIGN KEY (meal_discount_id) REFERENCES public.ambassador_meal_discounts(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_amb_claims_grant') THEN
    ALTER TABLE public.ambassador_milestone_claims
      ADD CONSTRAINT fk_amb_claims_grant
      FOREIGN KEY (grant_id) REFERENCES public.ambassador_grants(id);
  END IF;
END $$;

-- Move stale active discounts to 'expired'. Safe to call repeatedly; the
-- checkout path and the ambassador dashboard invoke it opportunistically, so
-- no new cron infrastructure is required for correctness.
CREATE OR REPLACE FUNCTION public.hg_expire_ambassador_discounts()
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_count integer;
BEGIN
  WITH moved AS (
    UPDATE public.ambassador_meal_discounts
    SET status = 'expired'
    WHERE status = 'active' AND expires_at < now() AND uses_remaining > 0
    RETURNING 1
  )
  SELECT count(*) INTO v_count FROM moved;
  RETURN COALESCE(v_count, 0);
END; $$;
REVOKE ALL ON FUNCTION public.hg_expire_ambassador_discounts() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_expire_ambassador_discounts() TO service_role;

-- Create one meal-discount bucket and, when p_grant_id is supplied, wire it
-- back onto its ambassador_grants row. Each call is an independent bucket,
-- which is what makes recurring biweekly rewards possible.
CREATE OR REPLACE FUNCTION public.hg_grant_ambassador_meal_discount(
  p_actor_id uuid,
  p_ambassador_id uuid,
  p_max_meal_value numeric,
  p_uses integer,
  p_validity_days integer,
  p_grant_id uuid DEFAULT NULL,
  p_source_note text DEFAULT NULL
)
RETURNS public.ambassador_meal_discounts
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_ambassador public.ambassadors;
  v_discount public.ambassador_meal_discounts;
  v_code text;
BEGIN
  SELECT * INTO v_ambassador FROM public.ambassadors
  WHERE profile_id = p_ambassador_id AND status = 'active';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ambassador_not_found' USING ERRCODE = 'P0002';
  END IF;
  IF p_max_meal_value <= 0 OR p_uses < 1 OR p_validity_days < 1 THEN
    RAISE EXCEPTION 'invalid_discount_parameters' USING ERRCODE = '23514';
  END IF;

  v_code := 'HG-' || upper(substring(replace(gen_random_uuid()::text, '-', '') FROM 1 FOR 8));

  INSERT INTO public.ambassador_meal_discounts
    (ambassador_id, grant_id, code, max_meal_value, uses_total,
     uses_remaining, status, source_note, expires_at, created_by)
  VALUES
    (p_ambassador_id, p_grant_id, v_code, p_max_meal_value, p_uses,
     p_uses, 'active', LEFT(COALESCE(p_source_note, ''), 500),
     now() + make_interval(days => p_validity_days), p_actor_id)
  RETURNING * INTO v_discount;

  IF p_grant_id IS NOT NULL THEN
    UPDATE public.ambassador_grants
    SET meal_discount_id = v_discount.id,
        expires_at = v_discount.expires_at,
        validity_days = p_validity_days
    WHERE id = p_grant_id;
  END IF;

  RETURN v_discount;
END; $$;
REVOKE ALL ON FUNCTION public.hg_grant_ambassador_meal_discount(uuid, uuid, numeric, integer, integer, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_grant_ambassador_meal_discount(uuid, uuid, numeric, integer, integer, uuid, text)
  TO service_role;

-- Atomic checkout redemption. Validates ownership, expiry and remaining uses,
-- records the redemption (one per order via the unique constraint) and
-- decrements the bucket. Delivery is never touched by this discount — the
-- caller applies the amount to food lines only.
CREATE OR REPLACE FUNCTION public.hg_redeem_ambassador_meal_discount(
  p_discount_id uuid,
  p_order_id uuid,
  p_ambassador_id uuid,
  p_amount numeric,
  p_meal_item_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_discount public.ambassador_meal_discounts;
  v_redemption_id uuid;
BEGIN
  PERFORM public.hg_expire_ambassador_discounts();

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
  IF v_discount.status = 'expired' OR v_discount.expires_at < now() THEN
    RAISE EXCEPTION 'meal_discount_expired' USING ERRCODE = '23514';
  END IF;
  IF v_discount.uses_remaining <= 0 OR v_discount.status <> 'active' THEN
    RAISE EXCEPTION 'meal_discount_no_uses_left' USING ERRCODE = '23514';
  END IF;
  IF p_amount <= 0 OR p_amount > v_discount.max_meal_value THEN
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

-- Restore a use after an early cancellation (before preparation). Idempotent:
-- a second call for the same order reports restored = false. Refunds after
-- preparation intentionally do NOT restore, preventing cancel/reorder abuse.
CREATE OR REPLACE FUNCTION public.hg_restore_ambassador_meal_discount(p_order_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
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
      status = CASE WHEN expires_at < now() THEN 'expired' ELSE 'active' END
  WHERE id = v_redemption.discount_id;

  RETURN jsonb_build_object(
    'restored', true,
    'discount_id', v_redemption.discount_id,
    'amount', v_redemption.amount
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_restore_ambassador_meal_discount(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_restore_ambassador_meal_discount(uuid) TO service_role;
