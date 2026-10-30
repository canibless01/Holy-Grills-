-- Reserve explicitly selected HP rewards on their order; reuse existing receipts and status-log metadata.
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
    v_final_total_amount NUMERIC;
    v_debit_result JSONB;
    v_redemption_updated INTEGER;

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
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) i
               WHERE (i->>'quantity')::integer IS NULL OR (i->>'quantity')::integer < 1) THEN
        RETURN jsonb_build_object('error', 'Item quantity must be a positive whole number');
    END IF;
    IF p_ordering_window_id IS NOT NULL THEN
        SELECT capacity INTO v_capacity FROM ordering_windows
          WHERE id=p_ordering_window_id AND campus_id=p_campus_id AND NOT is_closed;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('error', 'ORDERING_WINDOW_CLOSED');
        END IF;
        SELECT coalesce(sum(CASE WHEN is_squad_order THEN greatest(coalesce(squad_item_count,1),1) ELSE 1 END),0)
          INTO v_used FROM orders
         WHERE campus_id=p_campus_id AND ordering_window_id=p_ordering_window_id
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
      INTO v_used FROM orders WHERE campus_id=p_campus_id AND status NOT IN ('cancelled','refunded')
        AND CASE WHEN is_scheduled THEN (scheduled_for AT TIME ZONE 'Africa/Lagos')::date
                 ELSE (created_at AT TIME ZONE 'Africa/Lagos')::date END = v_target_date;
    IF v_capacity IS NOT NULL AND v_used + (CASE WHEN p_is_squad_order THEN greatest(p_squad_item_count,1) ELSE 1 END) > v_capacity THEN
        RETURN jsonb_build_object('error', 'Kitchen capacity reached for this date');
    END IF;
    FOR v_required IN SELECT (i->>'menu_item_id')::uuid AS item_id, sum((i->>'quantity')::integer) AS quantity
                         FROM jsonb_array_elements(p_items) i
                         WHERE NOT coalesce((i->>'is_addon')::boolean,false)
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
         WHERE oi.menu_item_id=v_required.item_id AND o.campus_id=p_campus_id AND o.status NOT IN ('cancelled','refunded')
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
          IF NOT FOUND OR (v_hp_receipt.result_snapshot->'reward_config'->>'multiplier')::numeric IS DISTINCT FROM v_hp_value THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
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
            IF NOT FOUND THEN RAISE EXCEPTION 'delivery_benefit_changed'; END IF;
            v_benefit_cap := round((v_benefit_receipt.result_snapshot->'reward_config'->>'cap')::numeric,2);
            IF v_benefit_cap IS NULL OR v_benefit_cap<=0 OR v_benefit_cap<>(v_benefit->>'cap')::numeric THEN
                RAISE EXCEPTION 'delivery_benefit_changed';
            END IF;
        ELSE RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
        IF (v_benefit->>'discount')::numeric IS DISTINCT FROM least(v_benefit_fee,v_benefit_cap)
           OR p_delivery_fee IS DISTINCT FROM greatest(0,v_benefit_fee-v_benefit_cap) THEN
            RAISE EXCEPTION 'delivery_benefit_changed';
        END IF;
    END IF;

    v_final_total_amount := p_total_amount;

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

    -- ### FIX (audit A1): pass campus context through to the wallet debit ###
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
        VALUES (p_promo_code_id, p_user_id, v_order_id, greatest(0,p_discount_amount-coalesce(p_squad_discount_amount,0)-v_lock_discount_applied), NOW());
        UPDATE promo_codes SET used_count = used_count + 1 WHERE id = p_promo_code_id;
    END IF;

    IF p_redemption_id IS NOT NULL THEN
        IF p_user_id IS NULL THEN
            RAISE EXCEPTION 'Guests cannot use a reward redemption';
        END IF;
        UPDATE reward_redemptions
           SET attached_order_id = v_order_id, used_at = NOW()
         WHERE id = p_redemption_id
           AND user_id = p_user_id
           AND attached_order_id IS NULL
           AND status = 'fulfilled';
        GET DIAGNOSTICS v_redemption_updated = ROW_COUNT;
        IF v_redemption_updated = 0 THEN
            RAISE EXCEPTION 'Reward redemption is not available (already used, not fulfilled, or not yours)';
        END IF;
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
    v_status_changed := v_target_status IS DISTINCT FROM v_order.status;
    v_restore_claims := v_order.status::text IN ('received','paid') AND v_target_status::text IN ('cancelled','refunded');
    IF v_restore_claims THEN
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
  v_hp_plan jsonb;
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
  SELECT metadata->'hp_bonus_plan' INTO v_hp_plan FROM public.order_status_logs
    WHERE order_id=p_order_id AND jsonb_typeof(metadata->'hp_bonus_plan')='object' ORDER BY created_at,id LIMIT 1;
  IF v_hp_plan IS NOT NULL THEN
    v_multiplier:=1;
    IF v_hp_plan->>'source'='spin' THEN
      SELECT * INTO v_receipt FROM public.exclusive_spin_fulfillments WHERE id=(v_hp_plan->>'receipt_id')::uuid
        AND user_id=p_user_id AND applied_order_id=p_order_id AND status='pending'
        AND result_snapshot->>'prize_type'='hp_multiplier' FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
      v_multiplier:=(v_receipt.result_snapshot->'reward_config'->>'multiplier')::numeric;
      IF v_multiplier IS DISTINCT FROM (v_hp_plan->>'multiplier')::numeric OR v_multiplier NOT BETWEEN 1.01 AND 10 THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
    ELSIF v_hp_plan->>'source' IS DISTINCT FROM 'none' THEN RAISE EXCEPTION 'hp_bonus_changed'; END IF;
  ELSE
    -- Compatibility for orders admitted before explicit reward selection.
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
  IF v_total_hp=0 AND v_receipt.id IS NOT NULL AND v_hp_plan IS NOT NULL THEN
    UPDATE public.exclusive_spin_fulfillments SET applied_order_id=NULL WHERE id=v_receipt.id;
  END IF;
  UPDATE public.orders SET hp_earned=v_total_hp,hp_credited_at=now(),updated_at=now()
    WHERE id=p_order_id RETURNING * INTO v_order;
  RETURN jsonb_build_object('success',true,'order_id',p_order_id,'hp_earned',v_total_hp,
    'owner_hp',v_owner_hp,'multiplier_applied',v_multiplier,'hp_credited_at',v_order.hp_credited_at);
END
$function$;
