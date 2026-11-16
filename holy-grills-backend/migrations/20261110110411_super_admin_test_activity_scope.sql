SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $guard$ BEGIN
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_auto_assign_order_to_batch' AND md5(pg_get_functiondef(p.oid))='aa29d802ef2c4a0b546f788fb1822a65') THEN RAISE EXCEPTION 'Source function changed: hg_auto_assign_order_to_batch'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND md5(pg_get_functiondef(p.oid))='72002a5cb166f52a9017068eebada596') THEN RAISE EXCEPTION 'Source function changed: hg_create_order_atomic'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_decrement_promo_used_count' AND md5(pg_get_functiondef(p.oid))='f72238d5a359229d4c30f8c483b9f0f5') THEN RAISE EXCEPTION 'Source function changed: hg_decrement_promo_used_count'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_refund_order_atomic' AND md5(pg_get_functiondef(p.oid))='952728ab425548ba1612aeb6cc8dbbb8') THEN RAISE EXCEPTION 'Source function changed: hg_refund_order_atomic'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_stage_ready_order_groups' AND md5(pg_get_functiondef(p.oid))='65f67c92116dbf0e38e088878d4af837') THEN RAISE EXCEPTION 'Source function changed: hg_stage_ready_order_groups'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_transfer_hp_atomic' AND md5(pg_get_functiondef(p.oid))='9212280b00cdafa788502cc513e2009d') THEN RAISE EXCEPTION 'Source function changed: hg_transfer_hp_atomic'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_wallet_transfer' AND md5(pg_get_functiondef(p.oid))='c0cdef0228f57af24694740a1c030800') THEN RAISE EXCEPTION 'Source function changed: hg_wallet_transfer'; END IF;
END $guard$;
-- Customer test activity is derived from the owner, never the staff editor.
ALTER TABLE public.orders ADD COLUMN is_test boolean NOT NULL DEFAULT false;
CREATE FUNCTION public.hg_classify_test_order() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 NEW.is_test := (CASE WHEN TG_OP='UPDATE' THEN OLD.is_test ELSE false END)
   OR EXISTS(SELECT 1 FROM public.profiles WHERE id=NEW.user_id AND role::text='super_admin');
 IF NEW.is_test AND TG_OP='UPDATE' AND (NEW.batch_id IS DISTINCT FROM OLD.batch_id AND NEW.batch_id IS NOT NULL) THEN
  RAISE EXCEPTION 'Test orders cannot enter real delivery batches';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_classify_test_order() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER aa_classify_test_order BEFORE INSERT OR UPDATE ON public.orders
 FOR EACH ROW EXECUTE FUNCTION public.hg_classify_test_order();
UPDATE public.orders o SET is_test=true FROM public.profiles p WHERE p.id=o.user_id AND p.role::text='super_admin' AND NOT o.is_test;
CREATE INDEX orders_real_campus_date ON public.orders(campus_id,created_at) WHERE NOT is_test;

CREATE VIEW public.reporting_orders WITH(security_invoker=true) AS SELECT t.* FROM public.orders t WHERE NOT t.is_test AND NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_orders FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_orders TO authenticated,service_role;

CREATE VIEW public.reporting_profiles WITH(security_invoker=true) AS SELECT t.* FROM public.profiles t WHERE t.role::text<>'super_admin';
REVOKE ALL ON public.reporting_profiles FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_profiles TO authenticated,service_role;

CREATE VIEW public.reporting_order_items WITH(security_invoker=true) AS SELECT t.* FROM public.order_items t WHERE EXISTS(SELECT 1 FROM public.orders o WHERE o.id=t.order_id AND NOT o.is_test AND NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=o.user_id AND p.role::text='super_admin'));
REVOKE ALL ON public.reporting_order_items FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_order_items TO authenticated,service_role;

CREATE VIEW public.reporting_wallet_transactions WITH(security_invoker=true) AS SELECT t.* FROM public.wallet_transactions t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_wallet_transactions FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_wallet_transactions TO authenticated,service_role;

CREATE VIEW public.reporting_hp_transactions WITH(security_invoker=true) AS SELECT t.* FROM public.hp_transactions t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_hp_transactions FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_hp_transactions TO authenticated,service_role;

CREATE VIEW public.reporting_abandoned_carts WITH(security_invoker=true) AS SELECT t.* FROM public.abandoned_carts t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_abandoned_carts FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_abandoned_carts TO authenticated,service_role;

CREATE VIEW public.reporting_first_order_gifts WITH(security_invoker=true) AS SELECT t.* FROM public.first_order_gifts t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_first_order_gifts FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_first_order_gifts TO authenticated,service_role;

CREATE VIEW public.reporting_marketplace_purchases WITH(security_invoker=true) AS SELECT t.* FROM public.marketplace_purchases t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_marketplace_purchases FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_marketplace_purchases TO authenticated,service_role;

CREATE VIEW public.reporting_redemption_cost_log WITH(security_invoker=true) AS SELECT t.* FROM public.redemption_cost_log t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_redemption_cost_log FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_redemption_cost_log TO authenticated,service_role;

CREATE VIEW public.reporting_event_tickets WITH(security_invoker=true) AS SELECT t.* FROM public.event_tickets t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t.user_id AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_event_tickets FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_event_tickets TO authenticated,service_role;

CREATE VIEW public.reporting_event_checkins WITH(security_invoker=true) AS SELECT t.* FROM public.event_checkins t WHERE EXISTS(SELECT 1 FROM public.event_tickets t2 WHERE t2.id=t.ticket_id AND NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id=t2.user_id AND p.role::text='super_admin'));
REVOKE ALL ON public.reporting_event_checkins FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_event_checkins TO authenticated,service_role;

CREATE VIEW public.reporting_referrals WITH(security_invoker=true) AS SELECT t.* FROM public.referrals t WHERE NOT EXISTS(SELECT 1 FROM public.profiles p WHERE p.id IN(t.referrer_id,t.referred_user_id) AND p.role::text='super_admin');
REVOKE ALL ON public.reporting_referrals FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.reporting_referrals TO authenticated,service_role;

CREATE OR REPLACE FUNCTION public.hg_auto_assign_order_to_batch(p_order_id uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_order public.orders%ROWTYPE;
    v_gate_id uuid;
    v_gate_name text;
    v_batch_id uuid;
    v_delivery_date date;
BEGIN
    -- Lock order before advisory/batch, matching manual and rider operations.
    -- Never lock another order while holding the group lock.
    SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
    IF NOT FOUND OR v_order.is_test OR v_order.status::text<>'ready'
       OR v_order.payment_status::text NOT IN ('paid','partially_refunded') THEN RETURN NULL; END IF;
    IF v_order.batch_id IS NOT NULL THEN RETURN v_order.batch_id; END IF;
    IF v_order.campus_id IS NULL OR v_order.delivery_window_id IS NULL
       OR v_order.delivery_location_id IS NULL
       OR EXISTS(SELECT 1 FROM public.delivery_assignments WHERE order_id=p_order_id)
       OR NOT EXISTS(SELECT 1 FROM public.delivery_windows WHERE id=v_order.delivery_window_id AND campus_id=v_order.campus_id)
       THEN RETURN NULL; END IF;
    IF v_order.delivery_type::text='off_campus' THEN
        v_gate_id:=v_order.delivery_location_id;
    ELSIF v_order.delivery_type::text='on_campus' THEN
        SELECT gate_id INTO v_gate_id FROM public.hostels
        WHERE id=v_order.delivery_location_id AND is_active
          AND (campus_id=v_order.campus_id OR campus_id IS NULL);
    END IF;
    SELECT name INTO v_gate_name FROM public.gates WHERE id=v_gate_id AND is_active
      AND (campus_id=v_order.campus_id OR campus_id IS NULL);
    IF NOT FOUND THEN RETURN NULL; END IF;
    v_delivery_date := (CASE WHEN v_order.is_scheduled THEN v_order.scheduled_for
        ELSE v_order.created_at END AT TIME ZONE 'Africa/Lagos')::date;
    IF v_delivery_date IS NULL THEN RETURN NULL; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('delivery-stage:'||v_order.campus_id::text||':'||v_gate_id::text||':'||v_order.delivery_window_id::text||':'||v_delivery_date::text,0));
    -- A concurrent manual assignment may have sealed the candidate while this
    -- SELECT waited. READ COMMITTED rechecks these predicates after row locking.
    SELECT b.id INTO v_batch_id FROM public.delivery_batches b
    WHERE campus_id=v_order.campus_id AND gate_id=v_gate_id
      AND delivery_window_id=v_order.delivery_window_id
      AND window_id=v_order.delivery_window_id AND status='open' AND rider_id IS NULL
      AND (b.delivery_date=v_delivery_date OR b.delivery_date IS NULL)
      -- A weekly window UUID is reused across delivery dates. Infer the date
      -- from existing membership; never reuse an empty or mixed-date group.
      AND EXISTS(SELECT 1 FROM public.orders o WHERE o.batch_id=b.id)
      AND NOT EXISTS(SELECT 1 FROM public.orders o WHERE o.batch_id=b.id
        AND (CASE WHEN o.is_scheduled THEN o.scheduled_for ELSE o.created_at END
             AT TIME ZONE 'Africa/Lagos')::date IS DISTINCT FROM v_delivery_date)
    ORDER BY b.created_at,b.id LIMIT 1 FOR UPDATE OF b;
    IF v_batch_id IS NULL THEN
        INSERT INTO public.delivery_batches(window_id,delivery_window_id,gate_id,zone,status,campus_id,delivery_date)
        VALUES(v_order.delivery_window_id,v_order.delivery_window_id,v_gate_id,coalesce(v_gate_name,''),'open',v_order.campus_id,v_delivery_date)
        RETURNING id INTO v_batch_id;
    END IF;
    UPDATE public.delivery_batches SET delivery_date=v_delivery_date
      WHERE id=v_batch_id AND delivery_date IS NULL;
    -- Staging leaves status READY, assigned_at empty, and no rider override.
    UPDATE public.orders SET batch_id=v_batch_id WHERE id=p_order_id;
    RETURN v_batch_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_stage_ready_order_groups()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE v_id uuid;
BEGIN
    -- Transition tables run after the kitchen statement has locked all affected
    -- orders. Sort group locks consistently for bulk operations. Nested helper
    -- batch_id writes and cancellation assigned->ready releases are ignored.
    IF TG_OP='INSERT' THEN
        FOR v_id IN
            SELECT n.id FROM hg_stage_new n
            LEFT JOIN public.hostels h ON n.delivery_type::text='on_campus' AND h.id=n.delivery_location_id
              AND (h.campus_id=n.campus_id OR h.campus_id IS NULL)
            WHERE NOT n.is_test AND n.status::text='ready' AND n.batch_id IS NULL
              AND n.payment_status::text IN ('paid','partially_refunded')
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,(CASE WHEN n.is_scheduled THEN n.scheduled_for ELSE n.created_at END AT TIME ZONE 'Africa/Lagos')::date,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    ELSE
        FOR v_id IN
            SELECT n.id FROM hg_stage_new n JOIN hg_stage_old o USING(id)
            LEFT JOIN public.hostels h ON n.delivery_type::text='on_campus' AND h.id=n.delivery_location_id
              AND (h.campus_id=n.campus_id OR h.campus_id IS NULL)
            WHERE NOT n.is_test AND n.status::text='ready' AND o.status::text='preparing'
              AND o.batch_id IS NULL AND n.batch_id IS NULL
              AND n.payment_status::text IN ('paid','partially_refunded')
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,(CASE WHEN n.is_scheduled THEN n.scheduled_for ELSE n.created_at END AT TIME ZONE 'Africa/Lagos')::date,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    END IF;
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_create_order_atomic(p_user_id uuid, p_guest_name text, p_guest_email citext, p_guest_phone text, p_claim_token uuid, p_subtotal numeric, p_delivery_fee numeric, p_discount_amount numeric, p_total_amount numeric, p_delivery_type text, p_delivery_location_id uuid, p_delivery_location_lat double precision, p_delivery_location_lon double precision, p_delivery_address_snapshot jsonb, p_delivery_window_id uuid, p_squad_name text, p_notes text, p_idempotency_key text, p_promo_code_id uuid, p_items jsonb, p_status order_status DEFAULT 'received'::order_status, p_payment_status payment_status DEFAULT 'pending'::payment_status, p_wallet_amount_used numeric DEFAULT 0, p_card_amount_used numeric DEFAULT 0, p_hp_redeemed integer DEFAULT 0, p_is_scheduled boolean DEFAULT false, p_scheduled_for timestamp with time zone DEFAULT NULL::timestamp with time zone, p_is_squad_order boolean DEFAULT false, p_squad_discount_amount numeric DEFAULT 0, p_squad_item_count integer DEFAULT 0, p_gift_included boolean DEFAULT false, p_order_lock_id uuid DEFAULT NULL::uuid, p_campus_id uuid DEFAULT NULL::uuid, p_squad_id uuid DEFAULT NULL::uuid, p_ordering_window_id uuid DEFAULT NULL::uuid, p_capacity_deferred boolean DEFAULT false, p_originally_requested_date date DEFAULT NULL::date, p_redemption_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_order_id UUID;
    v_order_item_id UUID;
    v_item JSONB;
    v_addon JSONB;
    v_lock_updated INTEGER;
    v_existing_order_id UUID;
    v_constraint_name TEXT;
    v_item_menu_item_id UUID;
    v_item_quantity INTEGER;
    v_item_name_snapshot TEXT;
    v_item_price_snapshot NUMERIC;
    v_item_hp_earn_snapshot INTEGER;
    v_item_hp_multiplier_snapshot NUMERIC;
    v_item_selected_variations JSONB;
    v_item_options_snapshot JSONB;
    v_item_line_total NUMERIC;
    v_item_is_addon BOOLEAN;
    v_lock_reward_type TEXT;
    v_lock_discount_pct NUMERIC;
    v_lock_hp_amount INTEGER;
    v_lock_discount_applied NUMERIC := 0;
    v_meal_plan jsonb; v_meal_result jsonb;
    v_promo public.promo_codes%ROWTYPE;
    v_final_total_amount NUMERIC;
    v_debit_result JSONB;
    v_redemption_updated INTEGER;
    v_reward_claims uuid[];
    v_reward_claim_id uuid;
    v_claim public.reward_redemptions%ROWTYPE;
    v_claim_reward public.rewards%ROWTYPE;
    v_claim_line jsonb;

    v_target_date DATE;
    v_capacity INTEGER;
    v_used NUMERIC;
    v_limit INTEGER;
    v_required RECORD;
    v_existing JSONB;
    v_hp_plan jsonb; v_hp_receipt public.exclusive_spin_fulfillments%ROWTYPE; v_hp_profile public.profiles%ROWTYPE; v_hp_value numeric;
    v_benefit jsonb; v_benefit_source text;
    v_benefit_profile public.profiles%ROWTYPE;
    v_benefit_receipt public.exclusive_spin_fulfillments%ROWTYPE;
    v_free_side_plan jsonb;
    v_free_side_result jsonb;
    v_benefit_cap numeric; v_benefit_fee numeric; v_perk_claim jsonb;
BEGIN
    IF p_user_id IS NOT NULL AND COALESCE(auth.role(), '') <> 'service_role' AND p_user_id IS DISTINCT FROM auth.uid() THEN
        RETURN jsonb_build_object('error', 'Unauthorized: cannot place an order for another user');
    END IF;

    IF p_user_id IS NULL AND p_guest_email IS NULL AND p_guest_phone IS NULL THEN
        RETURN jsonb_build_object('error', 'Guest checkout requires guest_email or guest_phone');
    END IF;

    IF p_user_id IS NULL AND (p_wallet_amount_used > 0 OR p_hp_redeemed > 0) THEN
        RETURN jsonb_build_object('error', 'Guests cannot use wallet or HP redemption');
    END IF;

    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RETURN jsonb_build_object('error', 'Order requires at least one item');
    END IF;

    IF p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
        RETURN jsonb_build_object('error', 'idempotency_key is required');
    END IF;


    -- Serialize admissions for one campus/day. Replays resolve before admission checks.
    IF p_campus_id IS NULL THEN
        RETURN jsonb_build_object('error', 'A campus is required for an order');
    END IF;
    v_target_date := CASE WHEN p_is_scheduled THEN (p_scheduled_for AT TIME ZONE 'Africa/Lagos')::date
                         ELSE (now() AT TIME ZONE 'Africa/Lagos')::date END;
    IF v_target_date IS NULL OR v_target_date < (now() AT TIME ZONE 'Africa/Lagos')::date THEN
        RETURN jsonb_build_object('error', 'A valid scheduled date is required');
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('hg-order:' || p_campus_id::text || ':' || v_target_date::text, 0));
    SELECT to_jsonb(o) INTO v_existing FROM orders o WHERE idempotency_key = p_idempotency_key;
    IF v_existing IS NOT NULL THEN
        IF (v_existing->>'user_id')::uuid IS DISTINCT FROM p_user_id OR
           (p_user_id IS NULL AND (lower(v_existing->>'guest_email') IS DISTINCT FROM lower(p_guest_email::text)
                                  OR v_existing->>'guest_phone' IS DISTINCT FROM p_guest_phone)) THEN
            RETURN jsonb_build_object('error', 'Checkout intent is not available');
        END IF;
        RETURN jsonb_build_object('success', true, 'order_id', v_existing->>'id',
                                  'total_amount', v_existing->'total_amount', 'idempotent', true);
    END IF;
    -- The server has already priced the basket. A payment split must cover
    -- exactly that price; an unknown payment method cannot create paid food.
    IF p_subtotal IS NULL OR p_delivery_fee IS NULL OR p_discount_amount IS NULL OR p_total_amount IS NULL
       OR p_wallet_amount_used IS NULL OR p_card_amount_used IS NULL
       OR EXISTS(SELECT 1 FROM unnest(ARRAY[p_subtotal,p_delivery_fee,p_discount_amount,p_total_amount,p_wallet_amount_used,p_card_amount_used]) amount
                 WHERE amount<0 OR amount::text IN ('NaN','Infinity','-Infinity'))
       OR p_discount_amount>p_subtotal
       OR p_total_amount<>p_subtotal-p_discount_amount+p_delivery_fee
       OR p_wallet_amount_used+p_card_amount_used<>p_total_amount THEN
        RETURN jsonb_build_object('error','ORDER_PAYMENT_CONSERVATION');
    END IF;
    IF p_promo_code_id IS NOT NULL THEN
        SELECT * INTO v_promo FROM public.promo_codes WHERE id=p_promo_code_id FOR UPDATE;
        IF NOT FOUND OR p_user_id IS NULL OR NOT v_promo.is_active
        OR (v_promo.campus_id IS NOT NULL AND v_promo.campus_id IS DISTINCT FROM p_campus_id)
        OR (v_promo.starts_at IS NOT NULL AND now()<v_promo.starts_at)
        OR (v_promo.ends_at IS NOT NULL AND now()>v_promo.ends_at)
        OR p_subtotal<coalesce(v_promo.min_order_amount,0)
        OR (v_promo.max_uses IS NOT NULL AND (SELECT count(*) FROM public.orders WHERE NOT is_test AND promo_code_id=p_promo_code_id AND status NOT IN ('cancelled','refunded'))>=v_promo.max_uses)
        OR (v_promo.max_uses_per_user IS NOT NULL AND (SELECT count(*) FROM public.orders WHERE promo_code_id=p_promo_code_id AND user_id=p_user_id AND status NOT IN ('cancelled','refunded'))>=v_promo.max_uses_per_user)
        THEN RETURN jsonb_build_object('error','promo_unavailable'); END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) i
               WHERE (i->>'quantity')::integer IS NULL OR (i->>'quantity')::integer < 1) THEN
        RETURN jsonb_build_object('error', 'Item quantity must be a positive whole number');
    END IF;
    -- Internal server plan, carried without adding an RPC overload. Lock every
    -- entitlement in UUID order before order creation or money movement.
    IF jsonb_typeof(coalesce(p_items->0->'_reward_claims','[]'::jsonb)) <> 'array' THEN
        RAISE EXCEPTION 'Reward redemption is not available';
    END IF;
    SELECT coalesce(array_agg(id ORDER BY id), ARRAY[]::uuid[]) INTO v_reward_claims
      FROM (SELECT DISTINCT value::uuid AS id
              FROM jsonb_array_elements_text(coalesce(p_items->0->'_reward_claims','[]'::jsonb))
            UNION SELECT p_redemption_id WHERE p_redemption_id IS NOT NULL) claims;
    IF cardinality(v_reward_claims)>0 AND p_user_id IS NULL THEN
        RAISE EXCEPTION 'Guests cannot use a reward redemption';
    END IF;
    IF cardinality(v_reward_claims)>0 THEN
        -- Match wallet -> entitlement ordering used by cancellation/refund.
        PERFORM 1 FROM public.wallets WHERE user_id=p_user_id FOR UPDATE;
    END IF;
    FOREACH v_reward_claim_id IN ARRAY v_reward_claims LOOP
        SELECT * INTO v_claim FROM public.reward_redemptions
         WHERE id=v_reward_claim_id FOR UPDATE;
        IF NOT FOUND OR v_claim.user_id IS DISTINCT FROM p_user_id
           OR v_claim.status<>'fulfilled' OR v_claim.attached_order_id IS NOT NULL
           OR v_claim.used_at IS NOT NULL
           OR (v_claim.campus_id IS NOT NULL AND v_claim.campus_id IS DISTINCT FROM p_campus_id)
           OR (v_reward_claim_id IS DISTINCT FROM p_redemption_id AND v_claim.delivery_mode<>'next_order') THEN
            RAISE EXCEPTION 'Reward redemption is not available';
        END IF;
        IF v_claim.reward_snapshot IS NOT NULL THEN
            SELECT * INTO v_claim_reward FROM jsonb_populate_record(NULL::public.rewards,v_claim.reward_snapshot);
        ELSE
            SELECT * INTO v_claim_reward FROM public.rewards WHERE id=v_claim.reward_id;
        END IF;
        IF NOT FOUND OR (v_claim_reward.campus_id IS NOT NULL AND v_claim_reward.campus_id IS DISTINCT FROM p_campus_id) THEN
            RAISE EXCEPTION 'Reward redemption is not available';
        END IF;
        IF (SELECT count(*) FROM jsonb_array_elements(p_items) i
             WHERE i->'options_snapshot'->>'reward_redemption_id'=v_reward_claim_id::text)<>1 THEN
            RAISE EXCEPTION 'Reward redemption is not available';
        END IF;
        SELECT i INTO v_claim_line FROM jsonb_array_elements(p_items) i
         WHERE i->'options_snapshot'->>'reward_redemption_id'=v_reward_claim_id::text;
        IF v_claim_line->>'name_snapshot' IS DISTINCT FROM v_claim_reward.name
           OR v_claim_line->'options_snapshot'->>'reward_name' IS DISTINCT FROM v_claim_reward.name
           OR (v_claim_line->>'quantity')::integer IS DISTINCT FROM 1
           OR (v_claim_line->>'price_snapshot')::numeric IS DISTINCT FROM 0
           OR (v_claim_line->>'line_total')::numeric IS DISTINCT FROM 0
           OR (v_claim_line->>'hp_earn_snapshot')::numeric IS DISTINCT FROM 0
           OR coalesce((v_claim_line->>'is_addon')::boolean,false)
           OR (v_claim_line->>'menu_item_id')::uuid IS DISTINCT FROM
              (v_claim_reward.metadata->>'menu_item_id')::uuid THEN
            RAISE EXCEPTION 'Reward redemption is not available';
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) i
                WHERE (i->'options_snapshot' ? 'reward_redemption_id'
                       AND NOT ((i->'options_snapshot'->>'reward_redemption_id')::uuid = ANY(v_reward_claims)))
                   OR (i->>'menu_item_id' IS NULL AND NOT coalesce((i->>'is_addon')::boolean,false)
                       AND NOT (coalesce(i->'options_snapshot'->>'reward_redemption_id','')=ANY(v_reward_claims::text[])))) THEN
        RAISE EXCEPTION 'Reward redemption is not available';
    END IF;

    IF p_ordering_window_id IS NOT NULL THEN
        SELECT ow.capacity INTO v_capacity FROM public.ordering_windows ow
          WHERE ow.id=p_ordering_window_id AND ow.campus_id=p_campus_id
          AND CASE
            WHEN ow.date IS NOT NULL THEN ow.date=v_target_date AND NOT ow.is_closed
            WHEN EXISTS(SELECT 1 FROM public.ordering_windows dated WHERE dated.campus_id=p_campus_id AND dated.date=v_target_date) THEN false
            WHEN EXISTS(SELECT 1 FROM public.operating_hour_overrides h WHERE h.date=v_target_date AND (h.campus_id=p_campus_id OR h.campus_id IS NULL)) THEN
              ow.weekday=extract(isodow FROM v_target_date)::integer-1
              AND (SELECT count(*) FROM public.ordering_windows weekly WHERE weekly.campus_id=p_campus_id AND weekly.date IS NULL AND weekly.weekday=ow.weekday)=1
              AND NOT (SELECT h.is_closed FROM public.operating_hour_overrides h WHERE h.date=v_target_date AND (h.campus_id=p_campus_id OR h.campus_id IS NULL) ORDER BY (h.campus_id IS NOT NULL) DESC LIMIT 1)
            ELSE ow.weekday=extract(isodow FROM v_target_date)::integer-1 AND NOT ow.is_closed
          END;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('error', 'ORDERING_WINDOW_CLOSED');
        END IF;
        SELECT coalesce(sum(CASE WHEN is_squad_order THEN greatest(coalesce(squad_item_count,1),1) ELSE 1 END),0)
          INTO v_used FROM orders
         WHERE NOT is_test AND campus_id=p_campus_id AND ordering_window_id=p_ordering_window_id
           AND status NOT IN ('cancelled','refunded')
           AND CASE WHEN is_scheduled THEN (scheduled_for AT TIME ZONE 'Africa/Lagos')::date
                    ELSE (created_at AT TIME ZONE 'Africa/Lagos')::date END = v_target_date;
        IF v_capacity IS NOT NULL AND v_used + (CASE WHEN p_is_squad_order THEN greatest(p_squad_item_count,1) ELSE 1 END) > v_capacity THEN
            RETURN jsonb_build_object('error', 'ORDERING_WINDOW_AT_CAPACITY');
        END IF;
    END IF;
    SELECT CASE WHEN value ~ '^[0-9]+$' THEN value::integer ELSE NULL END INTO v_capacity
      FROM kitchen_settings WHERE key='daily_order_capacity' AND campus_id=p_campus_id LIMIT 1;
    SELECT coalesce(sum(CASE WHEN is_squad_order THEN greatest(coalesce(squad_item_count,1),1) ELSE 1 END),0)
      INTO v_used FROM orders WHERE NOT is_test AND campus_id=p_campus_id AND status NOT IN ('cancelled','refunded')
        AND CASE WHEN is_scheduled THEN (scheduled_for AT TIME ZONE 'Africa/Lagos')::date
                 ELSE (created_at AT TIME ZONE 'Africa/Lagos')::date END = v_target_date;
    IF v_capacity IS NOT NULL AND v_used + (CASE WHEN p_is_squad_order THEN greatest(p_squad_item_count,1) ELSE 1 END) > v_capacity THEN
        RETURN jsonb_build_object('error', 'Kitchen capacity reached for this date');
    END IF;
    FOR v_required IN SELECT (i->>'menu_item_id')::uuid AS item_id, sum((i->>'quantity')::integer) AS quantity
                         FROM jsonb_array_elements(p_items) i
                         WHERE NOT coalesce((i->>'is_addon')::boolean,false)
                           AND i->>'menu_item_id' IS NOT NULL
                         GROUP BY (i->>'menu_item_id')::uuid
    LOOP
        SELECT coalesce(a.daily_limit,m.daily_limit) INTO v_limit
          FROM menu_items m LEFT JOIN menu_item_availability a ON a.menu_item_id=m.id AND a.campus_id=p_campus_id
         WHERE m.id=v_required.item_id AND (m.campus_id=p_campus_id OR m.campus_id IS NULL)
           AND m.is_available AND m.deleted_at IS NULL AND coalesce(a.is_available,true);
        IF NOT FOUND THEN
            RETURN jsonb_build_object('error', 'Menu item is unavailable for this campus');
        END IF;
        SELECT coalesce(sum(oi.quantity),0) INTO v_used FROM order_items oi JOIN orders o ON o.id=oi.order_id
         WHERE NOT o.is_test AND oi.menu_item_id=v_required.item_id AND o.campus_id=p_campus_id AND o.status NOT IN ('cancelled','refunded')
           AND CASE WHEN o.is_scheduled THEN (o.scheduled_for AT TIME ZONE 'Africa/Lagos')::date
                    ELSE (o.created_at AT TIME ZONE 'Africa/Lagos')::date END = v_target_date;
        IF v_limit IS NOT NULL AND v_used + v_required.quantity > v_limit THEN
            RETURN jsonb_build_object('error', 'Menu item daily limit reached');
        END IF;
    END LOOP;

    v_hp_plan:=p_items->0->'_hp_bonus_plan';
    IF v_hp_plan IS NOT NULL THEN
      IF jsonb_typeof(v_hp_plan)<>'object' OR v_hp_plan->>'source' NOT IN ('none','legacy','spin') OR v_hp_plan->>'source' IS NULL THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
      IF v_hp_plan->>'source'<>'none' THEN
        IF p_user_id IS NULL THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
        PERFORM 1 FROM public.wallets WHERE user_id=p_user_id FOR UPDATE;
        SELECT * INTO v_hp_profile FROM public.profiles WHERE id=p_user_id FOR UPDATE;
        IF NOT FOUND OR NOT v_hp_profile.is_active OR v_hp_profile.campus_id IS DISTINCT FROM p_campus_id THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
        v_hp_value:=(v_hp_plan->>'multiplier')::numeric;
        IF v_hp_value IS NULL OR v_hp_value NOT BETWEEN 1.01 AND 10 OR v_hp_value::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
        IF v_hp_plan->>'source'='legacy' THEN
          IF COALESCE(v_hp_profile.next_order_hp_multiplier,1)<>v_hp_value THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
        ELSE
          SELECT * INTO v_hp_receipt FROM public.exclusive_spin_fulfillments WHERE id=(v_hp_plan->>'receipt_id')::uuid
            AND user_id=p_user_id AND (campus_id=p_campus_id OR campus_id IS NULL) AND status='pending' AND applied_order_id IS NULL
            AND result_snapshot->>'prize_type'='hp_multiplier' FOR UPDATE;
          IF NOT FOUND OR (v_hp_receipt.result_snapshot->>'expires_at')::timestamptz<=now() OR (v_hp_receipt.result_snapshot->'reward_config'->>'multiplier')::numeric IS DISTINCT FROM v_hp_value THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
        END IF;
      END IF;
    END IF;

    v_benefit := p_items->0->'_delivery_benefit';
    v_benefit_source := COALESCE(v_benefit->>'source','none');
    IF v_benefit_source <> 'none' THEN
        IF p_user_id IS NULL THEN RAISE EXCEPTION 'delivery_benefit_changed'; END IF;
        -- Wallet -> profile matches the wallet balance mirror's lock order.
        PERFORM 1 FROM public.wallets WHERE user_id=p_user_id FOR UPDATE;
        SELECT * INTO v_benefit_profile FROM public.profiles WHERE id=p_user_id FOR UPDATE;
        IF NOT FOUND OR NOT v_benefit_profile.is_active OR v_benefit_profile.campus_id IS DISTINCT FROM p_campus_id THEN
            RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
        v_benefit_fee := (v_benefit->>'original_fee')::numeric;
        IF v_benefit_fee IS NULL OR v_benefit_fee<=0 OR v_benefit_fee::text IN ('NaN','Infinity','-Infinity') THEN
            RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
        IF v_benefit_source='monthly' THEN
            IF p_is_squad_order OR (v_benefit->>'month') IS DISTINCT FROM to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM')
               OR (v_benefit->>'tier_id')::uuid IS DISTINCT FROM v_benefit_profile.current_tier_id
               OR EXISTS(SELECT 1 FROM public.tier_monthly_perk_usage WHERE user_id=p_user_id
                  AND month=v_benefit->>'month' AND perk_key='monthly_free_delivery') THEN
                RAISE EXCEPTION 'delivery_benefit_changed';
            END IF;
            v_benefit_cap := v_benefit_fee;
        ELSIF v_benefit_source='legacy_spin' THEN
            v_benefit_cap := round(COALESCE(v_benefit_profile.next_order_free_delivery_cap,0),2);
            IF v_benefit_cap<=0 OR v_benefit_cap<>(v_benefit->>'cap')::numeric THEN
                RAISE EXCEPTION 'delivery_benefit_changed';
            END IF;
        ELSIF v_benefit_source='spin' THEN
            SELECT * INTO v_benefit_receipt FROM public.exclusive_spin_fulfillments
              WHERE id=(v_benefit->>'receipt_id')::uuid AND user_id=p_user_id AND campus_id=p_campus_id
                AND status='pending' AND applied_order_id IS NULL AND result_snapshot->>'prize_type'='free_delivery'
              FOR UPDATE;
            IF NOT FOUND OR (v_benefit_receipt.result_snapshot->>'expires_at')::timestamptz<=now() THEN RAISE EXCEPTION 'delivery_benefit_changed'; END IF;
            v_benefit_cap := round((v_benefit_receipt.result_snapshot->'reward_config'->>'cap')::numeric,2);
            IF v_benefit_cap IS NULL OR v_benefit_cap<=0 OR v_benefit_cap<>(v_benefit->>'cap')::numeric THEN
                RAISE EXCEPTION 'delivery_benefit_changed';
            END IF;
            IF coalesce((v_benefit_receipt.result_snapshot->'reward_config'->>'discount_pct')::numeric,1) NOT BETWEEN 0.01 AND 1 THEN
                RAISE EXCEPTION 'delivery_benefit_changed';
            END IF;
            v_benefit_cap:=least(v_benefit_cap,round(v_benefit_fee *
                coalesce((v_benefit_receipt.result_snapshot->'reward_config'->>'discount_pct')::numeric,1),2));
        ELSE RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
        IF (v_benefit->>'discount')::numeric IS DISTINCT FROM least(v_benefit_fee,v_benefit_cap)
           OR p_delivery_fee IS DISTINCT FROM greatest(0,v_benefit_fee-v_benefit_cap) THEN
            RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
    END IF;

    v_final_total_amount := p_total_amount;

    v_meal_plan:=p_items->0->'_ambassador_meal_discount';
    IF v_meal_plan IS NOT NULL THEN
      IF p_user_id IS NULL OR jsonb_typeof(v_meal_plan)<>'object'
         OR (v_meal_plan->>'amount')::numeric<=0
         OR (v_meal_plan->>'amount')::numeric>p_discount_amount
         OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p_items) i
                       WHERE i->>'menu_item_id'=v_meal_plan->>'meal_item_id'
                       AND NOT coalesce((i->>'is_addon')::boolean,false)
                       AND (i->>'price_snapshot')::numeric >= (v_meal_plan->>'amount')::numeric)
      THEN RAISE EXCEPTION 'ambassador_meal_discount_changed'; END IF;
    END IF;

    -- ### FIX (audit A1, D04/ORD-01+ORD-05): mark paid up-front when nothing is left owing on card ###
    IF p_card_amount_used = 0 THEN
        p_payment_status := 'paid'::payment_status;
        -- Payment completion is independent of kitchen preparation status.
        -- Keep received until kitchen starts preparing, including scheduled orders.
    END IF;
    -- ### END FIX ###

    BEGIN
        INSERT INTO orders (
            user_id, guest_name, guest_email, guest_phone,
            status, payment_status,
            subtotal, delivery_fee, discount_amount, total_amount,
            wallet_amount_used, card_amount_used, hp_redeemed,
            delivery_type, delivery_location_id, delivery_location_lat, delivery_location_lon,
            delivery_address_snapshot, delivery_window_id,
            is_scheduled, scheduled_for,
            is_squad_order, squad_name, squad_discount_amount, squad_item_count, squad_id,
            notes, gift_included, idempotency_key, promo_code_id,
            claim_token, created_at, updated_at, received_at, campus_id,
            ordering_window_id, capacity_deferred, originally_requested_date,
            redemption_id
        ) VALUES (
            p_user_id, p_guest_name, p_guest_email, p_guest_phone,
            p_status, p_payment_status,
            p_subtotal, p_delivery_fee, p_discount_amount, p_total_amount,
            p_wallet_amount_used, p_card_amount_used, p_hp_redeemed,
            p_delivery_type, p_delivery_location_id, p_delivery_location_lat, p_delivery_location_lon,
            p_delivery_address_snapshot, p_delivery_window_id,
            p_is_scheduled, p_scheduled_for,
            p_is_squad_order, p_squad_name, p_squad_discount_amount, p_squad_item_count, p_squad_id,
            p_notes, p_gift_included, p_idempotency_key, p_promo_code_id,
            p_claim_token, NOW(), NOW(),
            CASE WHEN p_is_scheduled = FALSE THEN NOW() ELSE NULL END,
            p_campus_id,
            p_ordering_window_id, p_capacity_deferred, p_originally_requested_date,
            p_redemption_id
        )
        RETURNING id INTO v_order_id;

    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;

        IF v_constraint_name = 'orders_idempotency_key_key' THEN
            SELECT id INTO v_existing_order_id FROM orders WHERE idempotency_key = p_idempotency_key;
            IF v_existing_order_id IS NULL THEN
                RAISE EXCEPTION 'Idempotency conflict detected but existing order was not found';
            END IF;
            RETURN jsonb_build_object('success', TRUE, 'order_id', v_existing_order_id, 'idempotent', TRUE);
        ELSE
            RAISE;
        END IF;
    END;

    IF v_benefit_source='monthly' THEN
        v_perk_claim := public.hg_claim_tier_monthly_perk(p_user_id,'monthly_free_delivery',v_benefit->>'month',v_order_id);
        IF NOT COALESCE((v_perk_claim->>'claimed')::boolean,false) THEN RAISE EXCEPTION 'delivery_benefit_changed'; END IF;
    ELSIF v_benefit_source='legacy_spin' THEN
        UPDATE public.profiles SET next_order_free_delivery_cap=0 WHERE id=p_user_id;
    ELSIF v_benefit_source='spin' THEN
        UPDATE public.exclusive_spin_fulfillments SET status='fulfilled',fulfilled_at=now(),applied_order_id=v_order_id
          WHERE id=v_benefit_receipt.id;
    END IF;
    IF v_hp_plan IS NOT NULL AND v_hp_plan->>'source'<>'none' THEN
      IF v_hp_plan->>'source'='legacy' THEN
        INSERT INTO public.exclusive_spin_fulfillments(user_id,campus_id,prize_name,status,applied_order_id,result_snapshot)
        VALUES(p_user_id,p_campus_id,v_hp_plan->>'name','pending',v_order_id,
          jsonb_build_object('prize_type','hp_multiplier','legacy',true,'reward_config',jsonb_build_object('kind','hp_multiplier','multiplier',v_hp_value)))
        RETURNING * INTO v_hp_receipt;
        UPDATE public.profiles SET next_order_hp_multiplier=1 WHERE id=p_user_id;
      ELSE
        UPDATE public.exclusive_spin_fulfillments SET applied_order_id=v_order_id WHERE id=v_hp_receipt.id;
      END IF;
      v_hp_plan:=v_hp_plan||jsonb_build_object('source','spin','receipt_id',v_hp_receipt.id);
    END IF;
    v_free_side_plan:=COALESCE(p_items->0->'_free_sides','[]'::jsonb);
    IF jsonb_typeof(v_free_side_plan)<>'array' THEN RAISE EXCEPTION 'free_side_selection_changed'; END IF;
    IF v_benefit_source<>'none' OR jsonb_array_length(v_free_side_plan)>0 OR v_hp_plan IS NOT NULL THEN
        INSERT INTO public.order_status_logs(order_id,status,metadata,campus_id)
          VALUES(v_order_id,p_status,jsonb_build_object('delivery_benefit',v_benefit,'free_side_plan',v_free_side_plan)||CASE WHEN v_hp_plan IS NOT NULL THEN jsonb_build_object('hp_bonus_plan',v_hp_plan) ELSE '{}'::jsonb END,p_campus_id);
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_item_menu_item_id := (v_item->>'menu_item_id')::UUID;
        v_item_quantity := (v_item->>'quantity')::INTEGER;
        v_item_name_snapshot := v_item->>'name_snapshot';
        v_item_price_snapshot := (v_item->>'price_snapshot')::NUMERIC;
        v_item_hp_earn_snapshot := COALESCE((v_item->>'hp_earn_snapshot')::INTEGER, 0);
        v_item_hp_multiplier_snapshot := COALESCE((v_item->>'hp_multiplier_snapshot')::NUMERIC, 1.0);
        v_item_selected_variations := v_item->'selected_variations';
        v_item_options_snapshot := COALESCE(v_item->'options_snapshot', '{}'::JSONB);
        v_item_line_total := (v_item->>'line_total')::NUMERIC;
        v_item_is_addon := COALESCE((v_item->>'is_addon')::BOOLEAN, FALSE);

        INSERT INTO order_items (
            order_id, menu_item_id, name_snapshot, price_snapshot,
            hp_earn_snapshot, hp_multiplier_snapshot, quantity,
            selected_variations, options_snapshot, line_total,
            is_addon, created_at, campus_id
        ) VALUES (
            v_order_id, v_item_menu_item_id, v_item_name_snapshot, v_item_price_snapshot,
            v_item_hp_earn_snapshot, v_item_hp_multiplier_snapshot, v_item_quantity,
            v_item_selected_variations, v_item_options_snapshot, v_item_line_total,
            v_item_is_addon, NOW(), p_campus_id
        )
        RETURNING id INTO v_order_item_id;

        IF v_item->'_addon_selections' IS NOT NULL AND jsonb_typeof(v_item->'_addon_selections') = 'array' THEN
            FOR v_addon IN SELECT * FROM jsonb_array_elements(v_item->'_addon_selections')
            LOOP
                INSERT INTO order_addon_selections (
                    order_item_id, addon_id, group_id, name_snapshot,
                    price_delta_snapshot, quantity, created_at, campus_id
                ) VALUES (
                    v_order_item_id,
                    (v_addon->>'addon_id')::UUID,
                    (v_addon->>'group_id')::UUID,
                    v_addon->>'name_snapshot',
                    COALESCE((v_addon->>'price_delta_snapshot')::NUMERIC, 0),
                    COALESCE((v_addon->>'quantity')::INTEGER, 1),
                    NOW(), p_campus_id
                );
            END LOOP;
        END IF;
    END LOOP;

    IF p_order_lock_id IS NOT NULL THEN
        UPDATE order_locks SET status = 'used', order_id = v_order_id, updated_at = NOW()
        WHERE id = p_order_lock_id AND user_id = p_user_id AND status = 'active'
          AND locked_date=(now() AT TIME ZONE 'Africa/Lagos')::date
          AND (campus_id=p_campus_id OR campus_id IS NULL);
        GET DIAGNOSTICS v_lock_updated = ROW_COUNT;
        IF v_lock_updated = 0 THEN
            RAISE EXCEPTION 'ORDER_LOCK_UNAVAILABLE';
        END IF;

        SELECT reward_type, discount_pct, reward_hp_amount
        INTO v_lock_reward_type, v_lock_discount_pct, v_lock_hp_amount
        FROM order_locks WHERE id = p_order_lock_id;

        IF v_lock_reward_type = 'discount' AND v_lock_discount_pct IS NOT NULL THEN
            -- Python prices the reward once, capped after other food discounts.
            -- Preserve its price rather than subtracting the lock a second time.
            v_lock_discount_applied := coalesce((p_items->0->>'_order_lock_discount_applied')::numeric,
                                                ROUND(p_subtotal*v_lock_discount_pct/100.0,2));
            IF v_lock_discount_pct NOT BETWEEN 1 AND 50 OR v_lock_discount_applied<0
               OR v_lock_discount_applied>ROUND(p_subtotal*v_lock_discount_pct/100.0,2)
               OR v_lock_discount_applied>p_discount_amount THEN
                RAISE EXCEPTION 'ORDER_LOCK_PRICING_MISMATCH';
            END IF;
        -- HP locks are reserved here; the existing order-update trigger credits
        -- their bonus atomically at delivery. Cancellation earns no spendable HP.
        END IF;
    END IF;

    IF jsonb_array_length(v_free_side_plan)>0 THEN
        IF p_user_id IS NULL THEN RAISE EXCEPTION 'free_side_selection_changed'; END IF;
        v_free_side_result:=public.hg_consume_free_sides_atomic(p_user_id,v_order_id,p_campus_id);
        IF (v_free_side_result->>'consumed')::integer IS DISTINCT FROM jsonb_array_length(v_free_side_plan) THEN
            RAISE EXCEPTION 'free_side_selection_changed';
        END IF;
    END IF;

    -- All claims are still locked. A later error rolls these writes and debits back.
    UPDATE public.reward_redemptions SET attached_order_id=v_order_id, used_at=now()
     WHERE id=ANY(v_reward_claims);

    -- ### FIX (audit A1): pass campus context through to the wallet debit ###
    IF v_meal_plan IS NOT NULL THEN
      v_meal_result:=public.hg_redeem_ambassador_meal_discount(
        (v_meal_plan->>'discount_id')::uuid,v_order_id,p_user_id,
        (v_meal_plan->>'amount')::numeric,(v_meal_plan->>'meal_item_id')::uuid);
      UPDATE public.orders SET ambassador_discount_id=(v_meal_plan->>'discount_id')::uuid WHERE id=v_order_id;
    END IF;

    IF p_wallet_amount_used > 0 AND p_user_id IS NOT NULL THEN
        v_debit_result := public.debit_wallet_atomic(p_user_id, p_wallet_amount_used, 'Order payment: ' || v_order_id::TEXT, 'order', v_order_id, '{}'::JSONB, p_campus_id);
        IF v_debit_result ? 'error' THEN
            RAISE EXCEPTION '%', v_debit_result->>'error';
        END IF;
    END IF;

    IF p_hp_redeemed > 0 AND p_user_id IS NOT NULL THEN
        -- ### FIX (audit A3): pass campus context through ###
        PERFORM public.hg_add_hp_transaction(p_user_id, 'spend', p_hp_redeemed, 'order_redemption', 'order', v_order_id, NULL, jsonb_build_object('source', 'hg_create_order_atomic'), NULL, p_campus_id);
    END IF;

    IF p_promo_code_id IS NOT NULL THEN
        INSERT INTO promo_code_uses (promo_code_id, user_id, order_id, discount_amount, created_at)
        VALUES (p_promo_code_id, p_user_id, v_order_id, coalesce((p_items->0->>'_promo_discount_amount')::numeric,greatest(0,p_discount_amount-coalesce(p_squad_discount_amount,0)-v_lock_discount_applied-coalesce((p_items->0->'_ambassador_meal_discount'->>'amount')::numeric,0))), NOW());
        UPDATE public.promo_codes SET used_count=(SELECT count(*) FROM public.orders WHERE NOT is_test AND promo_code_id=p_promo_code_id AND status::text NOT IN ('cancelled','refunded')) WHERE id=p_promo_code_id;
    END IF;

    RETURN jsonb_build_object('success', TRUE, 'order_id', v_order_id, 'status', p_status, 'total_amount', v_final_total_amount, 'order_lock_discount_applied', v_lock_discount_applied);

EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM, 'detail', SQLSTATE);
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_refund_order_atomic(p_order_id uuid, p_actor_id uuid, p_request_key text, p_requested_amount numeric DEFAULT NULL::numeric, p_reason text DEFAULT NULL::text, p_customer_cancel boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_order public.orders%ROWTYPE;
    v_actor public.profiles%ROWTYPE;
    v_existing public.wallet_transactions%ROWTYPE;
    v_provider_ref text;
    v_wallet_collected numeric;
    v_card_collected numeric;
    v_credited numeric;
    v_wallet_already numeric;
    v_card_already numeric;
    v_remaining numeric;
    v_amount numeric;
    v_wallet_alloc numeric;
    v_card_alloc numeric;
    v_credit jsonb;
    v_hp jsonb;
    v_target_status public.order_status;
    v_target_payment public.payment_status;
    v_status_changed boolean;
    v_restore_claims boolean;
    v_side_restore record;
BEGIN
    IF coalesce(auth.role(), '') <> 'service_role' THEN
        RETURN jsonb_build_object('success',false,'error','forbidden');
    END IF;
    IF p_request_key IS NULL OR btrim(p_request_key) = '' OR length(p_request_key) > 200 THEN
        RETURN jsonb_build_object('success',false,'error','invalid_intent');
    END IF;
    SELECT * INTO v_actor FROM public.profiles WHERE id=p_actor_id AND is_active;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','forbidden'); END IF;
    SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','order_not_found'); END IF;
    IF p_customer_cancel THEN
        IF v_order.user_id IS DISTINCT FROM p_actor_id THEN
            RETURN jsonb_build_object('success',false,'error','forbidden');
        END IF;
    ELSIF NOT (v_actor.role::text='super_admin' OR
               (v_actor.role::text='admin' AND v_actor.campus_id=v_order.campus_id)) THEN
        RETURN jsonb_build_object('success',false,'error','forbidden');
    END IF;
    IF v_order.user_id IS NULL THEN
        RETURN jsonb_build_object('success',false,'error','guest_refund_manual_required');
    END IF;
    -- Same promo -> wallet lock order as checkout.
    PERFORM 1 FROM public.promo_codes WHERE id=v_order.promo_code_id FOR UPDATE;
    v_provider_ref := 'order-refund-event:' || p_order_id::text || ':' || md5(p_request_key);
    SELECT * INTO v_existing FROM public.wallet_transactions
      WHERE user_id=v_order.user_id AND provider='internal-refund'
        AND provider_reference=v_provider_ref AND type='credit';
    IF FOUND THEN
        RETURN jsonb_build_object('success',true,'idempotent',true,'order_id',p_order_id,
            'refund_amount',v_existing.amount,'wallet_refunded',v_existing.amount,
            'status',v_order.status,'payment_status',v_order.payment_status,
            'transaction_id',v_existing.id);
    END IF;
    IF p_customer_cancel AND v_order.status::text NOT IN ('received','paid','cancelled') THEN
        RETURN jsonb_build_object('success',false,'error','cannot_cancel');
    END IF;
    -- The wallet is debited at creation. Card money exists only after payment
    -- confirmation; a pending card portion is never eligible for a refund.
    v_wallet_collected := coalesce(v_order.wallet_amount_used,0);
    v_card_collected := CASE WHEN v_order.payment_status::text IN ('paid','partially_refunded','refunded')
                            THEN coalesce(v_order.card_amount_used,0) ELSE 0 END;
    SELECT coalesce(sum(amount),0) INTO v_credited FROM public.wallet_transactions
      WHERE user_id=v_order.user_id AND type='credit' AND reference_type='refund' AND reference_id=p_order_id;
    IF v_credited > v_wallet_collected+v_card_collected THEN
        RETURN jsonb_build_object('success',false,'error','refund_conservation');
    END IF;
    -- Historical reserve-only counters are not proof that money was returned.
    -- Reconcile against the actual ledger while this order is locked.
    v_wallet_already := least(v_credited,v_wallet_collected);
    v_card_already := greatest(0,v_credited-v_wallet_already);
    v_remaining := v_wallet_collected+v_card_collected-v_credited;
    IF p_customer_cancel THEN
        v_amount := v_remaining;
    ELSE
        v_amount := coalesce(p_requested_amount,v_remaining);
        IF v_amount IS NULL OR v_amount::text IN ('NaN','Infinity','-Infinity') OR v_amount<=0 OR v_amount>v_remaining THEN
            RETURN jsonb_build_object('success',false,'error','invalid_amount','refundable_total',v_remaining);
        END IF;
    END IF;
    v_wallet_alloc := least(v_amount,greatest(0,v_wallet_collected-v_wallet_already));
    v_card_alloc := v_amount-v_wallet_alloc;
    IF v_amount>0 THEN
        v_credit := public.credit_wallet_atomic(v_order.user_id,v_amount,p_reason,'refund',p_order_id,
            'internal-refund',v_provider_ref,jsonb_build_object('actor_id',p_actor_id,
            'wallet_allocation',v_wallet_alloc,'card_allocation',v_card_alloc,
            'customer_cancel',p_customer_cancel),v_order.campus_id);
        IF NOT coalesce((v_credit->>'success')::boolean,false) OR v_credit ? 'error' THEN
            RAISE EXCEPTION 'Refund credit failed' USING ERRCODE='P0001';
        END IF;
    END IF;
    v_target_status := v_order.status;
    v_target_payment := v_order.payment_status;
    IF p_customer_cancel THEN
        v_target_status := 'cancelled'::public.order_status;
    ELSIF v_amount=v_remaining AND v_order.status::text NOT IN ('cancelled','refunded') THEN
        v_target_status := 'refunded'::public.order_status;
    END IF;
    IF v_amount=v_remaining THEN
        v_target_payment := CASE WHEN v_order.payment_status::text IN ('paid','partially_refunded','refunded')
                            THEN 'refunded'::public.payment_status ELSE 'failed'::public.payment_status END;
    ELSIF v_credited+v_amount>0 AND v_order.payment_status::text IN ('paid','partially_refunded') THEN
        v_target_payment := 'partially_refunded'::public.payment_status;
    END IF;
    IF v_amount=v_remaining AND v_order.status::text NOT IN ('cancelled','refunded')
      AND v_target_status::text IN ('cancelled','refunded') AND v_order.promo_code_id IS NOT NULL AND NOT v_order.is_test THEN
        UPDATE public.promo_codes SET used_count=greatest(0,used_count-1) WHERE id=v_order.promo_code_id;
    END IF;
    v_status_changed := v_target_status IS DISTINCT FROM v_order.status;
    v_restore_claims := v_order.status::text IN ('received','paid') AND v_target_status::text IN ('cancelled','refunded');
    IF v_restore_claims THEN
        PERFORM public.hg_restore_ambassador_meal_discount(p_order_id);
        IF coalesce(v_order.hp_redeemed,0)>0 THEN
            v_hp := public.record_hp_transaction_atomic(v_order.user_id,v_order.hp_redeemed,'earn','active',
                'order_refund','order',p_order_id,NULL,p_reason,v_order.campus_id);
            IF v_hp ? 'error' THEN RAISE EXCEPTION 'HP return failed' USING ERRCODE='P0001'; END IF;
        END IF;
        -- A selected food-HP bonus is reserved, not spent, until delivery.
        UPDATE public.exclusive_spin_fulfillments SET applied_order_id=NULL
          WHERE applied_order_id=p_order_id AND user_id=v_order.user_id AND status='pending'
            AND result_snapshot->>'prize_type'='hp_multiplier';
        UPDATE public.exclusive_spin_fulfillments SET status='pending',fulfilled_at=NULL,applied_order_id=NULL
          WHERE applied_order_id=p_order_id AND user_id=v_order.user_id AND result_snapshot->>'prize_type'='free_delivery';
        DELETE FROM public.tier_monthly_perk_usage WHERE reference_order_id=p_order_id AND user_id=v_order.user_id
          AND perk_key='monthly_free_delivery';
        -- Only the log for this exact cancelled order can restore a legacy cap.
        UPDATE public.profiles SET next_order_free_delivery_cap=greatest(COALESCE(next_order_free_delivery_cap,0),
            COALESCE((SELECT (metadata->'delivery_benefit'->>'cap')::numeric FROM public.order_status_logs
              WHERE order_id=p_order_id AND metadata->'delivery_benefit'->>'source'='legacy_spin' LIMIT 1),0))
          WHERE id=v_order.user_id;
        FOR v_side_restore IN
            SELECT (entry->>'credit_id')::uuid credit_id,count(*) amount
            FROM public.order_status_logs l CROSS JOIN LATERAL jsonb_array_elements(COALESCE(l.metadata->'free_sides_consumed','[]')) entry
            WHERE l.order_id=p_order_id AND NOT COALESCE((l.metadata->>'free_sides_restored')::boolean,false)
            GROUP BY (entry->>'credit_id')::uuid
        LOOP
            UPDATE public.free_side_credits SET credits_remaining=credits_remaining+v_side_restore.amount
              WHERE id=v_side_restore.credit_id AND user_id=v_order.user_id AND (campus_id IS NULL OR campus_id=v_order.campus_id);
            IF NOT FOUND THEN RAISE EXCEPTION 'free_side_refund_missing_credit'; END IF;
        END LOOP;
        UPDATE public.order_status_logs SET metadata=metadata||jsonb_build_object('free_sides_restored',true)
          WHERE order_id=p_order_id AND metadata ? 'free_sides_consumed' AND NOT COALESCE((metadata->>'free_sides_restored')::boolean,false);
        UPDATE public.reward_redemptions SET attached_order_id=NULL,used_at=NULL,updated_at=now()
          WHERE attached_order_id=p_order_id AND user_id=v_order.user_id;
        UPDATE public.order_locks SET status='active',order_id=NULL,updated_at=now()
          WHERE order_id=p_order_id AND status='used' AND user_id=v_order.user_id;
    END IF;
    UPDATE public.orders SET wallet_refund_total=v_wallet_already+v_wallet_alloc,
        card_refund_total=v_card_already+v_card_alloc,status=v_target_status,payment_status=v_target_payment,
        cancelled_at=CASE WHEN v_target_status::text='cancelled' THEN coalesce(cancelled_at,now()) ELSE cancelled_at END,
        refunded_at=CASE WHEN v_amount>0 THEN now() ELSE refunded_at END,
        batch_id=CASE WHEN v_target_status::text IN ('cancelled','refunded') THEN NULL ELSE batch_id END,
        notes=CASE WHEN v_amount>0 OR v_status_changed THEN concat_ws(' | ',nullif(notes,''),nullif(p_reason,'')) ELSE notes END,
        updated_at=now() WHERE id=p_order_id;
    IF v_status_changed THEN
        UPDATE public.order_status_logs SET changed_by=p_actor_id,note=p_reason,
            metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('from_status',v_order.status,'action','refund','amount',v_amount)
          WHERE id=(SELECT id FROM public.order_status_logs WHERE order_id=p_order_id AND status=v_target_status ORDER BY created_at DESC LIMIT 1);
    ELSIF v_amount>0 THEN
        INSERT INTO public.order_status_logs(order_id,status,changed_by,note,metadata,campus_id)
        VALUES(p_order_id,v_target_status,p_actor_id,p_reason,jsonb_build_object('action','partial_refund','amount',v_amount),v_order.campus_id);
    END IF;
    RETURN jsonb_build_object('success',true,'idempotent',v_amount=0 AND NOT v_status_changed,
        'order_id',p_order_id,'refund_amount',v_amount,'wallet_refunded',v_amount,
        'status',v_target_status,'payment_status',v_target_payment,'status_changed',v_status_changed,
        'transaction_id',v_credit->'transaction_id','remaining_refundable',v_remaining-v_amount);
EXCEPTION WHEN OTHERS THEN
    -- This exception block rolls the credit, counters and all claims back.
    RETURN jsonb_build_object('success',false,'error','refund_failed','debug_code',SQLSTATE);
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_decrement_promo_used_count()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
BEGIN
  IF EXISTS(SELECT 1 FROM public.orders WHERE id=OLD.order_id AND is_test) THEN RETURN OLD; END IF;
  UPDATE public.promo_codes
  SET used_count = GREATEST(used_count - 1, 0)
  WHERE id = OLD.promo_code_id;
  RETURN OLD;
END;
$function$;

CREATE OR REPLACE FUNCTION public.hg_wallet_transfer(p_action text, p_actor uuid DEFAULT NULL::uuid, p_id uuid DEFAULT NULL::uuid, p_data jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE s public.profiles%rowtype;r public.profiles%rowtype;t hg_internal.wallet_transfers%rowtype;
 ids uuid[];uid uuid;amount bigint;minimum numeric;maximum numeric;daily numeric;spent numeric;available numeric;
 enabled boolean;receipt jsonb;source_balance numeric;target_balance numeric;out_id uuid;in_id uuid;
 code text;memo text;result jsonb;day_start timestamptz;
BEGIN
 IF p_action='due' THEN
  WITH due AS (
   SELECT id FROM hg_internal.wallet_transfers WHERE NOT notifications_done AND next_notice_at<=now()
   ORDER BY next_notice_at LIMIT least(greatest(coalesce((p_data->>'limit')::integer,10),0),20) FOR UPDATE SKIP LOCKED
  ), claimed AS (UPDATE hg_internal.wallet_transfers wallet_outbox SET next_notice_at=now()+interval '15 minutes' FROM due WHERE wallet_outbox.id=due.id
   RETURNING wallet_outbox.id,wallet_outbox.sender_id,wallet_outbox.recipient_id,wallet_outbox.sender_name,wallet_outbox.recipient_name,wallet_outbox.amount_kobo)
  SELECT coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('sender_id',sender_profile.id,'recipient_id',recipient_profile.id)),'[]') INTO result
   FROM claimed c LEFT JOIN public.profiles sender_profile ON sender_profile.id=c.sender_id LEFT JOIN public.profiles recipient_profile ON recipient_profile.id=c.recipient_id;
  RETURN result;
 ELSIF p_action='notice' THEN
  SELECT jsonb_build_object('id',transfer_row.id,'sender_id',sender_profile.id,'recipient_id',recipient_profile.id,'sender_name',transfer_row.sender_name,'recipient_name',transfer_row.recipient_name,'amount_kobo',transfer_row.amount_kobo)
   INTO result FROM hg_internal.wallet_transfers transfer_row LEFT JOIN public.profiles sender_profile ON sender_profile.id=transfer_row.sender_id LEFT JOIN public.profiles recipient_profile ON recipient_profile.id=transfer_row.recipient_id
   WHERE transfer_row.id=p_id AND NOT transfer_row.notifications_done;
  RETURN result;
 ELSIF p_action='notified' THEN
  UPDATE hg_internal.wallet_transfers SET notifications_done=true WHERE id=p_id; RETURN '{}';
 END IF;
 SELECT * INTO s FROM public.profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND THEN RAISE EXCEPTION 'account_unavailable'; END IF;
 IF p_action='get' THEN
  receipt:=public.hg_wallet_transfer_receipt(p_actor,p_id);
  IF receipt IS NULL THEN RAISE EXCEPTION 'transfer_not_found'; END IF;
  RETURN receipt;
 END IF;
 IF p_action='send' THEN
  IF p_id IS NULL OR jsonb_typeof(p_data->'amount_kobo')<>'number' OR coalesce(p_data->>'amount_kobo','')!~'^[0-9]+$' THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  amount:=(p_data->>'amount_kobo')::bigint;code:=upper(btrim(p_data->>'recipient_code'));memo:=btrim(coalesce(p_data->>'note',''));
  IF amount NOT BETWEEN 1 AND 100000000000 OR length(memo)>200 OR code IS NULL OR length(code) NOT BETWEEN 3 AND 80 THEN RAISE EXCEPTION 'invalid_transfer'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-transfer-intent:'||p_id::text,0));
  SELECT * INTO t FROM hg_internal.wallet_transfers WHERE id=p_id;
  IF FOUND THEN
   IF t.sender_id IS DISTINCT FROM p_actor THEN RAISE EXCEPTION 'transfer_not_found'; END IF;
   IF t.recipient_id IS DISTINCT FROM (p_data->>'recipient_id')::uuid OR t.amount_kobo<>amount OR t.note<>memo OR upper(t.recipient_code)<>code THEN RAISE EXCEPTION 'transfer_intent_conflict'; END IF;
   RETURN public.hg_wallet_transfer_receipt(p_actor,t.id)||jsonb_build_object('replayed',true);
  END IF;
 END IF;
 IF s.campus_id IS NULL THEN RAISE EXCEPTION 'campus_required'; END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='wallet_transfer' AND (campus_id=s.campus_id OR campus_id IS NULL)
  ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF p_action<>'limits' AND NOT coalesce(enabled,false) THEN RAISE EXCEPTION 'transfers_paused'; END IF;
 minimum:=public.hg_wallet_transfer_limit('wallet_transfer_min_amount',s.campus_id,1);
 maximum:=public.hg_wallet_transfer_limit('wallet_transfer_max_amount',s.campus_id,1000000);
 daily:=public.hg_wallet_transfer_limit('wallet_transfer_daily_limit',s.campus_id,1000000);
 IF minimum>maximum THEN RAISE EXCEPTION 'transfer_configuration_unavailable'; END IF;
 day_start:=date_trunc('day',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos';
 IF p_action='limits' THEN
  SELECT coalesce(balance,0) INTO available FROM public.wallets WHERE user_id=s.id;
  SELECT coalesce(sum(amount_kobo),0)::numeric/100 INTO spent FROM hg_internal.wallet_transfers WHERE sender_id=s.id AND created_at>=day_start;
  RETURN jsonb_build_object('enabled',coalesce(enabled,false),'minimum_amount',minimum,'maximum_amount',maximum,
   'daily_limit',daily,'daily_remaining',greatest(0,daily-spent),'available_balance',coalesce(available,0),'fee',0,'same_campus_only',true,'my_code',s.referral_code);
 ELSIF p_action='lookup' THEN
  code:=btrim(coalesce(p_data->>'value',p_data->>'code'));
  IF coalesce(p_data->>'lookup_type','code')='code' THEN
   code:=upper(code);
   IF code IS NULL OR code!~'^[A-Z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'invalid_recipient_code'; END IF;
  ELSIF p_data->>'lookup_type'='email' THEN
   code:=lower(code);
   IF code IS NULL OR length(code)>254 OR code!~'^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSIF p_data->>'lookup_type'='phone' THEN
   IF code IS NULL OR code!~'^[1-9][0-9]{7,14}$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSE RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  SELECT array_agg(id) INTO ids FROM (
   SELECT id FROM public.profiles WHERE is_active AND campus_id=s.campus_id AND (role::text='super_admin')=(s.role::text='super_admin') AND
    CASE coalesce(p_data->>'lookup_type','code')
     WHEN 'code' THEN upper(referral_code)=code
     WHEN 'email' THEN lower(btrim(email::text))=code
     WHEN 'phone' THEN (CASE WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^2340[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^0[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^[0-9]{10}$' THEN '234'||regexp_replace(phone,'[+() .-]','','g') ELSE regexp_replace(phone,'[+() .-]','','g') END)=code
     ELSE false END LIMIT 2) candidates;
  IF coalesce(cardinality(ids),0)=0 THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  IF cardinality(ids)>1 THEN RAISE EXCEPTION 'recipient_ambiguous'; END IF;
  SELECT * INTO r FROM public.profiles WHERE id=ids[1];
  IF r.id=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
  IF coalesce(r.referral_code,'')!~'^[A-Za-z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  RETURN jsonb_build_object('id',r.id,'name',left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),'code',r.referral_code); ELSIF p_action<>'send' THEN RAISE EXCEPTION 'invalid_transfer_action'; END IF;
 uid:=(p_data->>'recipient_id')::uuid;
 IF uid IS NULL OR uid=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
 SELECT * INTO r FROM public.profiles WHERE id=uid AND is_active AND campus_id=s.campus_id AND upper(referral_code)=code;
 IF NOT FOUND OR (s.role::text='super_admin') IS DISTINCT FROM (r.role::text='super_admin') THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
 -- Same lock order for opposing transfers; coordinate wallet creation with
 -- existing card credits, then lock both wallets and profiles before movement.
 FOR uid IN SELECT unnest(ARRAY[s.id,r.id]) ORDER BY 1 LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-credit:'||uid::text,0));
 END LOOP;
 INSERT INTO public.wallets(user_id,balance,currency,campus_id)
  SELECT id,0,'NGN',campus_id FROM public.profiles WHERE id IN (s.id,r.id) ORDER BY id ON CONFLICT(user_id) DO NOTHING;
 PERFORM user_id FROM public.wallets WHERE user_id IN (s.id,r.id) ORDER BY user_id FOR UPDATE;
 PERFORM id FROM public.profiles WHERE id IN (s.id,r.id) ORDER BY id FOR UPDATE;
 SELECT * INTO s FROM public.profiles WHERE id=p_actor AND is_active;
 SELECT * INTO r FROM public.profiles WHERE id=(p_data->>'recipient_id')::uuid AND is_active;
 IF (s.role::text='super_admin') IS DISTINCT FROM (r.role::text='super_admin') OR s.id IS NULL OR r.id IS NULL OR s.campus_id IS NULL OR r.campus_id IS DISTINCT FROM s.campus_id OR upper(r.referral_code) IS DISTINCT FROM code THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='wallet_transfer' AND (campus_id=s.campus_id OR campus_id IS NULL)
  ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF NOT coalesce(enabled,false) THEN RAISE EXCEPTION 'transfers_paused'; END IF;
 SELECT balance INTO source_balance FROM public.wallets WHERE user_id=s.id AND currency='NGN';
 SELECT balance INTO target_balance FROM public.wallets WHERE user_id=r.id AND currency='NGN';
 IF source_balance IS NULL OR target_balance IS NULL OR source_balance::text IN ('NaN','Infinity','-Infinity') OR target_balance::text IN ('NaN','Infinity','-Infinity') THEN RAISE EXCEPTION 'wallet_unavailable'; END IF;
 -- Limits and spend are checked under the sender lock; concurrent sends cannot
 -- overdraw or each consume the same daily allowance.
 minimum:=public.hg_wallet_transfer_limit('wallet_transfer_min_amount',s.campus_id,1);
 maximum:=public.hg_wallet_transfer_limit('wallet_transfer_max_amount',s.campus_id,1000000);
 daily:=public.hg_wallet_transfer_limit('wallet_transfer_daily_limit',s.campus_id,1000000);
 IF minimum>maximum THEN RAISE EXCEPTION 'transfer_configuration_unavailable'; END IF;
 IF amount::numeric/100<minimum OR amount::numeric/100>maximum THEN RAISE EXCEPTION 'transfer_amount_out_of_range'; END IF;
 SELECT coalesce(sum(amount_kobo),0) INTO spent FROM hg_internal.wallet_transfers WHERE sender_id=s.id AND created_at>=day_start;
 IF spent+amount>daily*100 THEN RAISE EXCEPTION 'transfer_daily_limit'; END IF;
 IF source_balance<amount::numeric/100 THEN RAISE EXCEPTION 'insufficient_wallet_balance'; END IF;
 source_balance:=source_balance-amount::numeric/100;target_balance:=target_balance+amount::numeric/100;
 UPDATE public.wallets SET balance=source_balance,updated_at=now() WHERE user_id=s.id;
 UPDATE public.wallets SET balance=target_balance,updated_at=now() WHERE user_id=r.id;
 -- The existing wallets trigger keeps profiles.wallet_balance synchronized.
 INSERT INTO public.wallet_transactions(user_id,type,amount,balance_after,reason,reference_type,reference_id,provider,provider_reference,metadata,campus_id)
 VALUES(s.id,'debit',amount::numeric/100,source_balance,'Sent to '||left(coalesce(nullif(r.nickname,''),r.full_name,'Campus member'),100),
  'wallet_transfer',p_id,'internal','wallet-transfer:'||p_id||':out',jsonb_build_object('transfer_id',p_id,'counterparty_id',r.id),s.campus_id) RETURNING id INTO out_id;
 INSERT INTO public.wallet_transactions(user_id,type,amount,balance_after,reason,reference_type,reference_id,provider,provider_reference,metadata,campus_id)
 VALUES(r.id,'credit',amount::numeric/100,target_balance,'Received from '||left(coalesce(nullif(s.nickname,''),s.full_name,'Campus member'),100),
  'wallet_transfer',p_id,'internal','wallet-transfer:'||p_id||':in',jsonb_build_object('transfer_id',p_id,'counterparty_id',s.id),s.campus_id) RETURNING id INTO in_id;
 INSERT INTO hg_internal.wallet_transfers(id,sender_id,recipient_id,campus_id,amount_kobo,sender_name,recipient_name,sender_code,recipient_code,note,
  sender_transaction_id,recipient_transaction_id,sender_balance_after,recipient_balance_after)
 VALUES(p_id,s.id,r.id,s.campus_id,amount,left(coalesce(nullif(btrim(s.nickname),''),nullif(btrim(s.full_name),''),'Campus member'),100),
  left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),s.referral_code,r.referral_code,memo,out_id,in_id,source_balance,target_balance);
 RETURN public.hg_wallet_transfer_receipt(p_actor,p_id)||jsonb_build_object('replayed',false);
END $function$;

CREATE OR REPLACE FUNCTION public.hg_transfer_hp_atomic(p_sender_id uuid, p_recipient_id uuid, p_amount integer, p_notes text, p_campus_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_transfer_id uuid := gen_random_uuid();
  v_debit  jsonb;
  v_credit jsonb;
BEGIN
  IF COALESCE(auth.role(), '') <> 'service_role' AND auth.uid() IS DISTINCT FROM p_sender_id THEN
    RETURN jsonb_build_object('success', false, 'error', 'forbidden');
  END IF;

  IF p_amount IS NULL OR p_amount <= 0 THEN
    RETURN jsonb_build_object('success', false, 'error', 'amount must be a positive number');
  END IF;

  PERFORM id FROM public.profiles WHERE id IN (p_sender_id,p_recipient_id) ORDER BY id FOR UPDATE;
  IF (EXISTS(SELECT 1 FROM public.profiles WHERE id=p_sender_id AND role::text='super_admin'))
     IS DISTINCT FROM (EXISTS(SELECT 1 FROM public.profiles WHERE id=p_recipient_id AND role::text='super_admin')) THEN
    RETURN jsonb_build_object('success',false,'error','Test points cannot be transferred between test and customer accounts');
  END IF;
  v_debit := public.record_hp_transaction_atomic(
    p_user_id := p_sender_id,
    p_amount := -p_amount,
    p_type := 'spend',
    p_status := 'active',
    p_source := 'hp_transfer_sent',
    p_reference_type := 'hp_transfer',
    p_reference_id := v_transfer_id,
    p_issued_by_admin_id := NULL,
    p_notes := p_notes,
    p_campus_id := p_campus_id
  );
  IF v_debit ? 'error' THEN
    RETURN jsonb_build_object('success', false, 'error', v_debit->>'error');
  END IF;

  v_credit := public.record_hp_transaction_atomic(
    p_user_id := p_recipient_id,
    p_amount := p_amount,
    p_type := 'earn',
    p_status := 'active',
    p_source := 'hp_transfer_received',
    p_reference_type := 'hp_transfer',
    p_reference_id := v_transfer_id,
    p_issued_by_admin_id := NULL,
    p_notes := p_notes,
    p_campus_id := p_campus_id
  );
  IF v_credit ? 'error' THEN
    RAISE EXCEPTION 'transfer_credit_failed: %', v_credit->>'error';
  END IF;

  RETURN jsonb_build_object(
    'success', true, 'transfer_id', v_transfer_id,
    'sender_new_balance', v_debit->>'new_balance', 'recipient_new_balance', v_credit->>'new_balance'
  );
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$function$;

CREATE FUNCTION public.hg_classify_promoted_test_orders() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NEW.role::text='super_admin' AND OLD.role IS DISTINCT FROM NEW.role THEN
  UPDATE public.orders SET is_test=true WHERE user_id=NEW.id AND NOT is_test;
 END IF; RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_classify_promoted_test_orders() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER classify_promoted_test_orders AFTER UPDATE OF role ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.hg_classify_promoted_test_orders();
-- Repair only global promo counters affected by reclassified test orders.
UPDATE public.promo_codes p SET used_count=(SELECT count(*) FROM public.orders o WHERE o.promo_code_id=p.id AND NOT o.is_test AND o.status::text NOT IN ('cancelled','refunded'))
WHERE EXISTS(SELECT 1 FROM public.orders t WHERE t.promo_code_id=p.id AND t.is_test);

NOTIFY pgrst,'reload schema';
