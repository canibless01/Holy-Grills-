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
        WHERE id = p_order_lock_id AND user_id = p_user_id AND status = 'active';
        GET DIAGNOSTICS v_lock_updated = ROW_COUNT;
        IF v_lock_updated = 0 THEN
            RAISE EXCEPTION 'Order lock is no longer available (already used, expired, or cancelled)';
        END IF;

        SELECT reward_type, discount_pct, reward_hp_amount
        INTO v_lock_reward_type, v_lock_discount_pct, v_lock_hp_amount
        FROM order_locks WHERE id = p_order_lock_id;

        IF v_lock_reward_type = 'discount' AND v_lock_discount_pct IS NOT NULL THEN
            v_lock_discount_applied := ROUND(p_subtotal * v_lock_discount_pct / 100.0, 2);
            v_final_total_amount := GREATEST(p_total_amount - v_lock_discount_applied, 0);
            UPDATE orders
            SET discount_amount = discount_amount + v_lock_discount_applied,
                total_amount = v_final_total_amount
            WHERE id = v_order_id;
        ELSIF v_lock_reward_type = 'hp' AND v_lock_hp_amount IS NOT NULL AND p_user_id IS NOT NULL THEN
            -- ### FIX (audit A3): pass campus context through ###
            PERFORM public.hg_add_hp_transaction(
                p_user_id, 'earn', v_lock_hp_amount, 'order_lock_reward',
                'order_lock', p_order_lock_id, NULL,
                jsonb_build_object('order_id', v_order_id), NULL, p_campus_id
            );
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
        VALUES (p_promo_code_id, p_user_id, v_order_id, p_discount_amount, NOW());
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
$function$

