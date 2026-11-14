-- ============================================================================
-- Campus Ambassador Programme — 2/4 — tracking RPCs
-- ----------------------------------------------------------------------------
-- Last-click attribution with a rolling window (default 7 days, configurable
-- via system_settings.ambassador_attribution_window_days). All functions are
-- SECURITY DEFINER and executable by service_role only; the Flask routes are
-- the sole callers and enforce application role checks first.
--
-- These functions never write profiles.referred_by or public.referrals — the
-- original referral programme and its 75 HP rule are completely independent.
-- ============================================================================

-- Window length in days, read from the global (campus_id IS NULL) setting.
CREATE OR REPLACE FUNCTION public.hg_ambassador_window_days()
RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_days integer;
BEGIN
  SELECT value::integer INTO v_days
  FROM public.system_settings
  WHERE key = 'ambassador_attribution_window_days' AND campus_id IS NULL;
  RETURN COALESCE(v_days, 7);
EXCEPTION WHEN OTHERS THEN
  RETURN 7;
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_window_days() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_window_days() TO service_role;

-- Resolve an active ambassador from a referral code. Returns NULL when the
-- code is unknown or belongs to a user without an active ambassador tag.
CREATE OR REPLACE FUNCTION public.hg_ambassador_for_code(p_ref_code text)
RETURNS TABLE (ambassador_id uuid, campus_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
  SELECT a.profile_id, a.campus_id
  FROM public.profiles p
  JOIN public.ambassadors a ON a.profile_id = p.id AND a.status = 'active'
  WHERE p.referral_code = upper(btrim(p_ref_code))
  LIMIT 1;
$$;
REVOKE ALL ON FUNCTION public.hg_ambassador_for_code(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_for_code(text) TO service_role;

-- Record one link hit and, for an identified visitor, refresh their current
-- last-click attribution. Anonymous hits are persisted with anonymous_id and
-- materialised later by hg_ambassador_merge_visitor after login/signup.
CREATE OR REPLACE FUNCTION public.hg_ambassador_record_click(
  p_ref_code text,
  p_visitor_user_id uuid DEFAULT NULL,
  p_anonymous_id text DEFAULT NULL,
  p_campus_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_ambassador uuid;
  v_campus uuid;
  v_window integer := public.hg_ambassador_window_days();
  v_expires timestamptz;
BEGIN
  SELECT ambassador_id, campus_id INTO v_ambassador, v_campus
  FROM public.hg_ambassador_for_code(p_ref_code);

  IF v_ambassador IS NULL THEN
    -- Unknown/inactive code: persist nothing, let the caller treat as a no-op.
    RETURN jsonb_build_object('attributed', false, 'reason', 'unknown_code');
  END IF;

  INSERT INTO public.ambassador_link_clicks
    (ref_code, ambassador_id, visitor_user_id, anonymous_id, campus_id)
  VALUES
    (upper(btrim(p_ref_code)), v_ambassador, p_visitor_user_id,
     NULLIF(btrim(p_anonymous_id), ''), COALESCE(p_campus_id, v_campus));

  IF p_visitor_user_id IS NOT NULL THEN
    v_expires := now() + make_interval(days => v_window);
    INSERT INTO public.ambassador_attributions AS att
      (customer_user_id, ambassador_id, first_click_at, last_click_at,
       expires_at, click_count)
    VALUES
      (p_visitor_user_id, v_ambassador, now(), now(), v_expires, 1)
    ON CONFLICT (customer_user_id) DO UPDATE
      -- Last click wins, including a click on the SAME ambassador (refresh).
      SET ambassador_id = EXCLUDED.ambassador_id,
          last_click_at = EXCLUDED.last_click_at,
          expires_at = EXCLUDED.expires_at,
          click_count = att.click_count + 1;
  END IF;

  RETURN jsonb_build_object(
    'attributed', true,
    'ambassador_id', v_ambassador,
    'window_days', v_window,
    'expires_at', v_expires
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_record_click(text, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_record_click(text, uuid, text, uuid) TO service_role;

-- Attach an anonymous click trail to the user who just logged in/signed up,
-- then build their attribution from the most recent anonymous click if it is
-- newer than anything already recorded. Idempotent: repeat calls only adopt
-- clicks still lacking a visitor.
CREATE OR REPLACE FUNCTION public.hg_ambassador_merge_visitor(
  p_anonymous_id text,
  p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_adopted integer;
  v_latest record;
  v_window integer := public.hg_ambassador_window_days();
BEGIN
  IF NULLIF(btrim(p_anonymous_id), '') IS NULL OR p_user_id IS NULL THEN
    RETURN jsonb_build_object('adopted_clicks', 0, 'attributed', false);
  END IF;

  WITH adopted AS (
    UPDATE public.ambassador_link_clicks c
    SET visitor_user_id = p_user_id
    WHERE c.anonymous_id = btrim(p_anonymous_id)
      AND c.visitor_user_id IS NULL
    RETURNING 1
  )
  SELECT count(*) INTO v_adopted FROM adopted;

  -- Most recent click across the adopted trail (any ambassador in it).
  SELECT ambassador_id, created_at INTO v_latest
  FROM public.ambassador_link_clicks
  WHERE anonymous_id = btrim(p_anonymous_id) AND visitor_user_id = p_user_id
  ORDER BY created_at DESC
  LIMIT 1;

  IF v_latest.ambassador_id IS NOT NULL THEN
    INSERT INTO public.ambassador_attributions AS att
      (customer_user_id, ambassador_id, first_click_at, last_click_at,
       expires_at, click_count)
    VALUES
      (p_user_id, v_latest.ambassador_id, v_latest.created_at,
       v_latest.created_at, v_latest.created_at + make_interval(days => v_window), 1)
    ON CONFLICT (customer_user_id) DO UPDATE
      SET ambassador_id = CASE
            WHEN EXCLUDED.last_click_at > att.last_click_at THEN EXCLUDED.ambassador_id
            ELSE att.ambassador_id END,
          first_click_at = LEAST(att.first_click_at, EXCLUDED.first_click_at),
          last_click_at = GREATEST(att.last_click_at, EXCLUDED.last_click_at),
          expires_at = GREATEST(att.expires_at,
                       EXCLUDED.last_click_at + make_interval(days => v_window)),
          click_count = att.click_count + 1;
  END IF;

  RETURN jsonb_build_object(
    'adopted_clicks', COALESCE(v_adopted, 0),
    'attributed', v_latest.ambassador_id IS NOT NULL
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_merge_visitor(text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_merge_visitor(text, uuid) TO service_role;

-- Attribute a delivered order to the customer's currently valid ambassador.
-- Called from the order lifecycle when an order reaches 'delivered'. The
-- primary key on order_id makes replay safe; a refund flips eligibility via
-- hg_ambassador_reverse_order rather than deleting the row.
CREATE OR REPLACE FUNCTION public.hg_ambassador_attribute_order(p_order_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_order record;
  v_attribution record;
BEGIN
  SELECT id, user_id, campus_id, total_amount, status, payment_status, created_at
  INTO v_order
  FROM public.orders
  WHERE id = p_order_id;

  IF NOT FOUND OR v_order.user_id IS NULL THEN
    RETURN jsonb_build_object('attributed', false, 'reason', 'order_not_found_or_guest');
  END IF;

  -- Eligibility: delivered and not fully refunded. Partial refunds stay eligible.
  IF v_order.status <> 'delivered'
     OR COALESCE(v_order.payment_status, '') = 'refunded' THEN
    RETURN jsonb_build_object('attributed', false, 'reason', 'order_ineligible');
  END IF;

  -- Window is evaluated against the ORDER timestamp using the attribution row
  -- as it existed when the order was placed: the qualifying click must
  -- predate the order and the window must still have covered the order.
  SELECT att.* INTO v_attribution
  FROM public.ambassador_attributions att
  JOIN public.ambassadors a ON a.profile_id = att.ambassador_id AND a.status = 'active'
  WHERE att.customer_user_id = v_order.user_id
    AND att.last_click_at <= v_order.created_at
    AND att.expires_at >= v_order.created_at
  ORDER BY att.last_click_at DESC
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('attributed', false, 'reason', 'no_live_attribution');
  END IF;

  INSERT INTO public.ambassador_order_attributions
    (order_id, customer_user_id, ambassador_id, campus_id, order_total, eligibility)
  VALUES
    (p_order_id, v_order.user_id, v_attribution.ambassador_id,
     v_order.campus_id, COALESCE(v_order.total_amount, 0), 'eligible')
  ON CONFLICT (order_id) DO UPDATE
    -- A re-run after a reversed refund restores eligibility.
    SET eligibility = 'eligible',
        exclusion_reason = NULL,
        order_total = EXCLUDED.order_total;

  RETURN jsonb_build_object(
    'attributed', true,
    'ambassador_id', v_attribution.ambassador_id,
    'order_id', p_order_id
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_attribute_order(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_attribute_order(uuid) TO service_role;

-- Mark an attributed order excluded (full refund / cancellation). Idempotent.
CREATE OR REPLACE FUNCTION public.hg_ambassador_reverse_order(
  p_order_id uuid,
  p_reason text DEFAULT 'order_refunded'
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE
  v_row public.ambassador_order_attributions;
BEGIN
  UPDATE public.ambassador_order_attributions
  SET eligibility = 'excluded',
      exclusion_reason = LEFT(COALESCE(p_reason, 'order_refunded'), 300)
  WHERE order_id = p_order_id AND eligibility = 'eligible'
  RETURNING * INTO v_row;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('reversed', false);
  END IF;
  RETURN jsonb_build_object('reversed', true, 'ambassador_id', v_row.ambassador_id);
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_reverse_order(uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_reverse_order(uuid, text) TO service_role;
