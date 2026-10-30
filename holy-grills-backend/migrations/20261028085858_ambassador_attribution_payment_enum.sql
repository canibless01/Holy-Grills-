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
     OR COALESCE(v_order.payment_status::text, '') NOT IN ('paid','partially_refunded') THEN
    RETURN jsonb_build_object('attributed', false, 'reason', 'order_ineligible');
  END IF;

  -- Window is evaluated against the ORDER timestamp using the attribution row
  -- as it existed when the order was placed: the qualifying click must
  -- predate the order and the window must still have covered the order.
  SELECT c.ambassador_id INTO v_attribution
  FROM public.ambassador_link_clicks c
  JOIN public.ambassadors a ON a.profile_id=c.ambassador_id AND a.status='active'
  WHERE c.visitor_user_id=v_order.user_id AND c.ambassador_id<>v_order.user_id
    AND c.created_at<=v_order.created_at
    AND c.created_at + make_interval(days=>public.hg_ambassador_window_days()) >= v_order.created_at
  ORDER BY c.created_at DESC,c.id DESC LIMIT 1;

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
    SET order_total = EXCLUDED.order_total;

  RETURN jsonb_build_object(
    'attributed', true,
    'ambassador_id', (SELECT ambassador_id FROM public.ambassador_order_attributions WHERE order_id=p_order_id),
    'order_id', p_order_id
  );
END; $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_attribute_order(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_attribute_order(uuid) TO service_role;

