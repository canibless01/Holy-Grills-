-- Workstream B: existing event definitions only; no shared ledger/role/task changes.
CREATE OR REPLACE FUNCTION public.get_event_tier_comparison(p_event_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY INVOKER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_result jsonb;
BEGIN
    SELECT jsonb_agg(
        jsonb_build_object(
            'id', id, 'name', name, 'description', description,
            'price_naira', price_naira, 'price_hp', price_hp,
            'features', COALESCE(features, '[]'::jsonb),
            'terms', COALESCE(terms, '[]'::jsonb),
            'color', color, 'icon', icon,
            'is_early_bird', COALESCE(is_early_bird, false),
            'early_bird_deadline', early_bird_deadline,
            'capacity', capacity, 'sold_count', sold_count,
            'available', CASE WHEN capacity IS NULL THEN NULL ELSE capacity - sold_count END,
            'is_sold_out', CASE WHEN capacity IS NULL THEN false ELSE sold_count >= capacity END
        ) ORDER BY price_naira ASC
    ) INTO v_result
    FROM event_ticket_tiers
    WHERE event_id = p_event_id AND is_active = true;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$function$;

CREATE OR REPLACE FUNCTION public.register_for_event_guest_paid(p_event_id uuid, p_guest_email citext, p_guest_name text, p_guest_phone text DEFAULT NULL::text, p_tier_id uuid DEFAULT NULL::uuid, p_promo_code_id uuid DEFAULT NULL::uuid, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_capacity integer;
  v_issued integer;
  v_ticket_id uuid;
  v_existing uuid;
  v_status text;
  v_event_campus_id uuid;
  v_ends_at timestamptz;
  v_tier_sold_count integer;
  v_tier_capacity integer;
  v_tier_active boolean;
  v_tier_early_bird boolean;
  v_tier_early_deadline timestamptz;
  v_price_naira_full numeric(14,2) := 0;
  v_discount numeric(14,2) := 0;
  v_total_naira numeric(14,2) := 0;
  v_payment_status text;
  v_ticket_status text;
  v_payment_expires_at timestamptz;
  v_promo record;
BEGIN
  IF p_guest_email IS NULL THEN
    RAISE EXCEPTION USING MESSAGE = 'guest_email is required', ERRCODE = 'P0001';
  END IF;

  SELECT COALESCE(capacity, max_attendees), campus_id, ends_at INTO v_capacity, v_event_campus_id, v_ends_at
  FROM events WHERE id = p_event_id AND is_published = true FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING MESSAGE = 'Event not found', ERRCODE = 'P0001';
  END IF;

  IF v_ends_at IS NOT NULL AND v_ends_at < now() THEN
    RAISE EXCEPTION USING MESSAGE = 'This event has already ended', ERRCODE = 'P0001';
  END IF;

  -- Duplicate-registration check (previously missing entirely for guests)
  SELECT id, status INTO v_existing, v_status
  FROM event_tickets
  WHERE event_id = p_event_id AND guest_email = p_guest_email AND status NOT IN ('cancelled','canceled','expired')
    AND NOT (status = 'pending_payment' AND payment_expires_at IS NOT NULL AND payment_expires_at < now())
  LIMIT 1;

  IF FOUND THEN
    RETURN (SELECT jsonb_build_object('ticket_id', id, 'status', status, 'payment_status', payment_status,
      'payment_method', payment_method, 'hp_charged', hp_amount_paid, 'wallet_amount_used', wallet_amount_used,
      'card_amount_used', card_amount_used, 'discount_amount', discount_amount, 'payment_expires_at', payment_expires_at,
      'already_registered', true) FROM public.event_tickets WHERE id=v_existing);
  END IF;

  IF v_capacity IS NOT NULL THEN
    SELECT COUNT(*) INTO v_issued FROM event_tickets
    WHERE event_id = p_event_id AND status NOT IN ('cancelled','canceled','expired')
      AND NOT (status = 'pending_payment' AND payment_expires_at IS NOT NULL AND payment_expires_at < now());
    IF v_issued >= v_capacity THEN
      RAISE EXCEPTION USING MESSAGE = 'Event is at full capacity', ERRCODE = 'P0001';
    END IF;
  END IF;

  IF p_tier_id IS NOT NULL THEN
    SELECT sold_count, capacity, COALESCE(price_naira_full, price_naira),
           is_active, is_early_bird, early_bird_deadline
      INTO v_tier_sold_count, v_tier_capacity, v_price_naira_full,
           v_tier_active, v_tier_early_bird, v_tier_early_deadline
    FROM event_ticket_tiers WHERE id = p_tier_id AND event_id = p_event_id FOR UPDATE;

    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'Ticket tier not found for this event', ERRCODE = 'P0001';
    END IF;

    IF NOT COALESCE(v_tier_active, true) THEN
      RAISE EXCEPTION USING MESSAGE = 'This ticket tier is no longer available', ERRCODE = 'P0001';
    END IF;

    IF COALESCE(v_tier_early_bird, false) AND v_tier_early_deadline IS NOT NULL AND v_tier_early_deadline < now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Early bird pricing for this tier has expired', ERRCODE = 'P0001';
    END IF;

    IF v_tier_capacity IS NOT NULL AND v_tier_sold_count >= v_tier_capacity THEN
      RAISE EXCEPTION USING MESSAGE = 'Tier at capacity', ERRCODE = 'P0001';
    END IF;

    UPDATE event_ticket_tiers SET sold_count = sold_count + 1, updated_at = now() WHERE id = p_tier_id;
  END IF;

  v_total_naira := COALESCE(v_price_naira_full, 0);

  IF p_promo_code_id IS NOT NULL AND v_total_naira > 0 THEN
    SELECT * INTO v_promo FROM promo_codes WHERE id = p_promo_code_id FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code not found', ERRCODE = 'P0001';
    END IF;
    IF NOT v_promo.is_active THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code is inactive', ERRCODE = 'P0001';
    END IF;
    IF v_promo.starts_at IS NOT NULL AND v_promo.starts_at > now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code is not yet active', ERRCODE = 'P0001';
    END IF;
    IF v_promo.ends_at IS NOT NULL AND v_promo.ends_at < now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code has expired', ERRCODE = 'P0001';
    END IF;
    IF v_promo.max_uses IS NOT NULL AND v_promo.used_count >= v_promo.max_uses THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code usage limit reached', ERRCODE = 'P0001';
    END IF;
    IF v_total_naira < COALESCE(v_promo.min_order_amount, 0) THEN
      RAISE EXCEPTION USING MESSAGE = 'Ticket price does not meet the minimum for this promo code', ERRCODE = 'P0001';
    END IF;

    IF v_promo.discount_type = 'percentage' THEN
      v_discount := round(v_total_naira * v_promo.discount_value / 100, 2);
    ELSE
      v_discount := v_promo.discount_value;
    END IF;
    v_discount := LEAST(v_discount, v_total_naira);

    UPDATE promo_codes SET used_count = used_count + 1 WHERE id = p_promo_code_id;
  END IF;

  v_total_naira := GREATEST(0, v_total_naira - v_discount);

  IF v_total_naira > 0 THEN
    v_payment_status := 'pending';
    v_ticket_status := 'pending_payment';
    v_payment_expires_at := now() + interval '30 minutes';
  ELSE
    v_payment_status := 'not_required';
    v_ticket_status := 'confirmed';
    v_payment_expires_at := NULL;
  END IF;

  INSERT INTO event_tickets (
    event_id, guest_email, guest_name, guest_phone, is_guest, status, campus_id, tier_id, metadata,
    price_naira, card_amount_used, discount_amount, promo_code_id, payment_method, payment_status, payment_expires_at
  )
  VALUES (
    p_event_id, p_guest_email, p_guest_name, p_guest_phone, TRUE, v_ticket_status, v_event_campus_id, p_tier_id, COALESCE(p_metadata, '{}'::jsonb),
    v_total_naira + v_discount, v_total_naira, v_discount, p_promo_code_id,
    CASE WHEN v_total_naira > 0 THEN 'card' ELSE 'none' END, v_payment_status, v_payment_expires_at
  )
  RETURNING id INTO v_ticket_id;

  IF p_promo_code_id IS NOT NULL AND v_discount > 0 THEN
    INSERT INTO promo_code_uses (promo_code_id, user_id, ticket_id, discount_amount, created_at, campus_id)
    VALUES (p_promo_code_id, NULL, v_ticket_id, v_discount, now(), v_event_campus_id);
  END IF;

  RETURN jsonb_build_object(
    'ticket_id', v_ticket_id, 'status', v_ticket_status, 'payment_status', v_payment_status,
    'card_amount_used', v_total_naira, 'discount_amount', v_discount,
    'payment_expires_at', v_payment_expires_at, 'already_registered', FALSE
  );
EXCEPTION WHEN SQLSTATE 'P0001' THEN
  -- This exception boundary rolls back tier, promo, HP and wallet mutations
  -- made by this invocation before returning its recoverable error.
  RETURN jsonb_build_object('error', SQLERRM);
END;
$function$;

CREATE OR REPLACE FUNCTION public.register_for_event_paid(p_event_id uuid, p_user_id uuid, p_tier_id uuid DEFAULT NULL::uuid, p_use_hp boolean DEFAULT false, p_wallet_amount numeric DEFAULT 0, p_promo_code_id uuid DEFAULT NULL::uuid, p_metadata jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_capacity integer;
  v_issued integer;
  v_ticket_id uuid;
  v_existing uuid;
  v_status text;
  v_event_campus_id uuid;
  v_ends_at timestamptz;
  v_tier_sold_count integer;
  v_tier_capacity integer;
  v_tier_active boolean;
  v_tier_early_bird boolean;
  v_tier_early_deadline timestamptz;
  v_price_naira numeric(14,2) := 0;
  v_price_naira_full numeric(14,2) := 0;
  v_price_hp integer := 0;
  v_cash_due numeric(14,2) := 0;
  v_discount numeric(14,2) := 0;
  v_card_amount numeric(14,2) := 0;
  v_wallet_amount numeric(14,2) := 0;
  v_hp_charged integer := 0;
  v_payment_method text;
  v_payment_status text;
  v_ticket_status text;
  v_payment_expires_at timestamptz;
  v_promo record;
  v_user_uses integer;
BEGIN
  IF COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
    RAISE EXCEPTION USING MESSAGE = 'Unauthorized: cannot register another user', ERRCODE = 'P0001';
  END IF;

  SELECT COALESCE(capacity, max_attendees), campus_id, ends_at INTO v_capacity, v_event_campus_id, v_ends_at
  FROM events WHERE id = p_event_id AND is_published = true FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING MESSAGE = 'Event not found', ERRCODE = 'P0001';
  END IF;

  IF v_ends_at IS NOT NULL AND v_ends_at < now() THEN
    RAISE EXCEPTION USING MESSAGE = 'This event has already ended', ERRCODE = 'P0001';
  END IF;

  IF p_wallet_amount IS NOT NULL AND (p_wallet_amount < 0 OR p_wallet_amount::text IN ('NaN','Infinity','-Infinity')) THEN
    RAISE EXCEPTION USING MESSAGE = 'Invalid wallet amount', ERRCODE = 'P0001';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.profiles WHERE id=p_user_id AND is_active=true AND (v_event_campus_id IS NULL OR campus_id=v_event_campus_id)) THEN
    RAISE EXCEPTION USING MESSAGE = 'Event not available to this account', ERRCODE = 'P0001';
  END IF;

  SELECT id, status INTO v_existing, v_status
  FROM event_tickets
  WHERE event_id = p_event_id AND user_id = p_user_id AND status NOT IN ('cancelled','canceled','expired')
    AND NOT (status = 'pending_payment' AND payment_expires_at IS NOT NULL AND payment_expires_at < now())
  LIMIT 1;

  IF FOUND THEN
    RETURN (SELECT jsonb_build_object('ticket_id', id, 'status', status, 'payment_status', payment_status,
      'payment_method', payment_method, 'hp_charged', hp_amount_paid, 'wallet_amount_used', wallet_amount_used,
      'card_amount_used', card_amount_used, 'discount_amount', discount_amount, 'payment_expires_at', payment_expires_at,
      'already_registered', true) FROM public.event_tickets WHERE id=v_existing);
  END IF;

  IF v_capacity IS NOT NULL THEN
    SELECT COUNT(*) INTO v_issued FROM event_tickets
    WHERE event_id = p_event_id AND status NOT IN ('cancelled','canceled','expired')
      AND NOT (status = 'pending_payment' AND payment_expires_at IS NOT NULL AND payment_expires_at < now());
    IF v_issued >= v_capacity THEN
      RAISE EXCEPTION USING MESSAGE = 'Event is at full capacity', ERRCODE = 'P0001';
    END IF;
  END IF;

  IF p_tier_id IS NOT NULL THEN
    SELECT sold_count, capacity, price_naira, price_hp, COALESCE(price_naira_full, price_naira),
           is_active, is_early_bird, early_bird_deadline
      INTO v_tier_sold_count, v_tier_capacity, v_price_naira, v_price_hp, v_price_naira_full,
           v_tier_active, v_tier_early_bird, v_tier_early_deadline
    FROM event_ticket_tiers WHERE id = p_tier_id AND event_id = p_event_id FOR UPDATE;

    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'Ticket tier not found for this event', ERRCODE = 'P0001';
    END IF;

    IF NOT COALESCE(v_tier_active, true) THEN
      RAISE EXCEPTION USING MESSAGE = 'This ticket tier is no longer available', ERRCODE = 'P0001';
    END IF;

    IF COALESCE(v_tier_early_bird, false) AND v_tier_early_deadline IS NOT NULL AND v_tier_early_deadline < now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Early bird pricing for this tier has expired', ERRCODE = 'P0001';
    END IF;

    IF v_tier_capacity IS NOT NULL AND v_tier_sold_count >= v_tier_capacity THEN
      RAISE EXCEPTION USING MESSAGE = 'Tier at capacity', ERRCODE = 'P0001';
    END IF;

    UPDATE event_ticket_tiers SET sold_count = sold_count + 1, updated_at = now() WHERE id = p_tier_id;
  END IF;

  IF COALESCE(v_price_naira_full, 0) = 0 AND COALESCE(v_price_hp, 0) = 0 THEN
    INSERT INTO event_tickets (event_id, user_id, status, campus_id, tier_id, metadata, price_naira, payment_method, payment_status)
    VALUES (p_event_id, p_user_id, 'confirmed', v_event_campus_id, p_tier_id, COALESCE(p_metadata, '{}'::jsonb), 0, 'none', 'not_required')
    RETURNING id INTO v_ticket_id;

    RETURN jsonb_build_object('ticket_id', v_ticket_id, 'status', 'confirmed', 'payment_status', 'not_required', 'already_registered', FALSE);
  END IF;

  IF p_use_hp THEN
    IF COALESCE(v_price_hp, 0) <= 0 THEN
      RAISE EXCEPTION USING MESSAGE = 'This ticket has no HP discount available', ERRCODE = 'P0001';
    END IF;
    PERFORM public.hg_add_hp_transaction(
      p_user_id, 'spend', v_price_hp, 'event_registration', 'event', p_event_id, null,
      jsonb_build_object('tier_id', p_tier_id), null, v_event_campus_id
    );
    v_hp_charged := v_price_hp;
    v_cash_due := COALESCE(v_price_naira, 0);
  ELSE
    v_cash_due := COALESCE(v_price_naira_full, 0);
  END IF;

  IF p_promo_code_id IS NOT NULL AND v_cash_due > 0 THEN
    SELECT * INTO v_promo FROM promo_codes WHERE id = p_promo_code_id FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code not found', ERRCODE = 'P0001';
    END IF;
    IF NOT v_promo.is_active THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code is inactive', ERRCODE = 'P0001';
    END IF;
    IF v_promo.starts_at IS NOT NULL AND v_promo.starts_at > now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code is not yet active', ERRCODE = 'P0001';
    END IF;
    IF v_promo.ends_at IS NOT NULL AND v_promo.ends_at < now() THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code has expired', ERRCODE = 'P0001';
    END IF;
    IF v_promo.max_uses IS NOT NULL AND v_promo.used_count >= v_promo.max_uses THEN
      RAISE EXCEPTION USING MESSAGE = 'Promo code usage limit reached', ERRCODE = 'P0001';
    END IF;
    IF v_cash_due < COALESCE(v_promo.min_order_amount, 0) THEN
      RAISE EXCEPTION USING MESSAGE = 'Ticket price does not meet the minimum for this promo code', ERRCODE = 'P0001';
    END IF;
    IF v_promo.max_uses_per_user IS NOT NULL THEN
      SELECT COUNT(*) INTO v_user_uses FROM event_tickets
      WHERE user_id = p_user_id AND promo_code_id = p_promo_code_id AND status <> 'cancelled';
      IF v_user_uses >= v_promo.max_uses_per_user THEN
        RAISE EXCEPTION USING MESSAGE = 'You have reached your usage limit for this promo code', ERRCODE = 'P0001';
      END IF;
    END IF;

    IF v_promo.discount_type = 'percentage' THEN
      v_discount := round(v_cash_due * v_promo.discount_value / 100, 2);
    ELSE
      v_discount := v_promo.discount_value;
    END IF;
    v_discount := LEAST(v_discount, v_cash_due);

    UPDATE promo_codes SET used_count = used_count + 1 WHERE id = p_promo_code_id;
  END IF;

  v_cash_due := GREATEST(0, v_cash_due - v_discount);
  v_wallet_amount := LEAST(GREATEST(COALESCE(p_wallet_amount, 0), 0), v_cash_due);
  v_card_amount := GREATEST(0, v_cash_due - v_wallet_amount);

  IF v_card_amount > 0 THEN
    v_payment_method := CASE
      WHEN v_hp_charged > 0 AND v_wallet_amount > 0 THEN 'hp_wallet_card'
      WHEN v_hp_charged > 0 THEN 'hp_card'
      WHEN v_wallet_amount > 0 THEN 'split'
      ELSE 'card'
    END;
    v_payment_status := 'pending';
    v_ticket_status := 'pending_payment';
    v_payment_expires_at := now() + interval '30 minutes';
  ELSE
    v_payment_method := CASE
      WHEN v_hp_charged > 0 AND v_wallet_amount > 0 THEN 'hp_wallet'
      WHEN v_hp_charged > 0 THEN 'hp'
      ELSE 'wallet'
    END;
    v_payment_status := 'paid';
    v_ticket_status := 'confirmed';
    v_payment_expires_at := NULL;
  END IF;

  IF v_wallet_amount > 0 THEN
    PERFORM public.hg_add_wallet_transaction(
      p_user_id, 'debit', v_wallet_amount, 'Event ticket payment', 'event', p_event_id, null, null, null,
      jsonb_build_object('tier_id', p_tier_id), v_event_campus_id
    );
  END IF;

  INSERT INTO event_tickets (
    event_id, user_id, status, campus_id, tier_id, metadata,
    price_naira, wallet_amount_used, card_amount_used, discount_amount,
    promo_code_id, payment_method, payment_status, pay_with_hp, hp_amount_paid, payment_expires_at
  )
  VALUES (
    p_event_id, p_user_id, v_ticket_status, v_event_campus_id, p_tier_id, COALESCE(p_metadata, '{}'::jsonb),
    v_cash_due + v_discount, v_wallet_amount, v_card_amount, v_discount,
    p_promo_code_id, v_payment_method, v_payment_status, v_hp_charged > 0, v_hp_charged, v_payment_expires_at
  )
  RETURNING id INTO v_ticket_id;

  IF p_promo_code_id IS NOT NULL AND v_discount > 0 THEN
    INSERT INTO promo_code_uses (promo_code_id, user_id, ticket_id, discount_amount, created_at, campus_id)
    VALUES (p_promo_code_id, p_user_id, v_ticket_id, v_discount, now(), v_event_campus_id);
  END IF;

  RETURN jsonb_build_object(
    'ticket_id', v_ticket_id,
    'status', v_ticket_status,
    'payment_status', v_payment_status,
    'payment_method', v_payment_method,
    'hp_charged', v_hp_charged,
    'wallet_amount_used', v_wallet_amount,
    'card_amount_used', v_card_amount,
    'discount_amount', v_discount,
    'payment_expires_at', v_payment_expires_at,
    'already_registered', FALSE
  );
EXCEPTION WHEN SQLSTATE 'P0001' THEN
  -- This exception boundary rolls back tier, promo, HP and wallet mutations
  -- made by this invocation before returning its recoverable error.
  RETURN jsonb_build_object('error', SQLERRM);
END;
$function$;

DROP POLICY IF EXISTS event_tiers_visible_parent ON public.event_ticket_tiers;
CREATE POLICY event_tiers_visible_parent ON public.event_ticket_tiers AS RESTRICTIVE FOR SELECT TO anon, authenticated
USING (EXISTS (SELECT 1 FROM public.events e WHERE e.id = event_ticket_tiers.event_id));
REVOKE ALL ON FUNCTION public.register_for_event_paid(uuid,uuid,uuid,boolean,numeric,uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_for_event_paid(uuid,uuid,uuid,boolean,numeric,uuid,jsonb) TO service_role;
REVOKE ALL ON FUNCTION public.register_for_event_guest_paid(uuid,citext,text,text,uuid,uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.register_for_event_guest_paid(uuid,citext,text,text,uuid,uuid,jsonb) TO service_role;
