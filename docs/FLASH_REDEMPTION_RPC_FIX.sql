CREATE OR REPLACE FUNCTION public.hg_redeem_flash_reward_atomic(p_user_id uuid, p_reward_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_flash flash_redemptions%ROWTYPE;
    v_reward rewards%ROWTYPE;
    v_redeemed_count INTEGER;
    v_discounted_cost INTEGER;
    v_redemption_id UUID;
    v_hp_result JSONB;
    v_current_balance INTEGER;
    v_user_tier_sort INTEGER;
    v_min_tier_sort INTEGER;
    v_user_redeem_count INTEGER;
    v_user_campus UUID;
    v_feature_enabled BOOLEAN;
BEGIN
    -- D01 hardening (matches hg_redeem_reward): a caller may only act for themselves
    -- (the server, using the service role, may act for anyone). Without this, anon or
    -- any authenticated user could pass an arbitrary p_user_id directly via PostgREST.
    IF COALESCE(auth.role(), '') <> 'service_role' AND auth.uid() IS DISTINCT FROM p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'forbidden');
    END IF;

    SELECT campus_id INTO v_user_campus FROM public.profiles WHERE id = p_user_id AND is_active;
    IF NOT FOUND OR v_user_campus IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'campus_required');
    END IF;
    SELECT is_active INTO v_feature_enabled FROM public.feature_flags
      WHERE feature_name = 'flash_redemptions' AND (campus_id = v_user_campus OR campus_id IS NULL)
      ORDER BY (campus_id IS NOT NULL) DESC LIMIT 1;
    IF NOT coalesce(v_feature_enabled, false) THEN
        RETURN jsonb_build_object('success', false, 'error', 'feature_disabled');
    END IF;
    SELECT * INTO v_flash FROM public.flash_redemptions
      WHERE reward_id = p_reward_id AND is_active = true
        AND (campus_id = v_user_campus OR campus_id IS NULL)
        AND window_starts_at <= now() AND (window_ends_at IS NULL OR window_ends_at >= now())
      ORDER BY (campus_id IS NOT NULL) DESC, window_starts_at DESC LIMIT 1 FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'no_active_sale');
    END IF;
    IF v_flash.window_ends_at IS NOT NULL AND v_flash.window_ends_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'window_closed');
    END IF;
    IF v_flash.window_starts_at IS NOT NULL AND v_flash.window_starts_at > now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'window_not_started');
    END IF;

    SELECT * INTO v_reward FROM rewards WHERE id = p_reward_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'reward_not_found');
    END IF;
    IF v_reward.campus_id IS NOT NULL AND v_reward.campus_id IS DISTINCT FROM v_user_campus THEN
        RETURN jsonb_build_object('success', false, 'error', 'reward_not_found');
    END IF;
    IF NOT v_reward.is_active THEN
        RETURN jsonb_build_object('success', false, 'error', 'inactive');
    END IF;
    IF v_reward.expires_at IS NOT NULL AND v_reward.expires_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'expired');
    END IF;
    IF v_reward.stock_quantity IS NOT NULL AND v_reward.stock_quantity <= 0 THEN
        RETURN jsonb_build_object('success', false, 'error', 'out_of_stock');
    END IF;
    IF v_reward.min_tier_id IS NOT NULL THEN
        SELECT ht.sort_order INTO v_user_tier_sort FROM profiles p
        LEFT JOIN hp_tiers ht ON ht.id = p.current_tier_id WHERE p.id = p_user_id;
        SELECT sort_order INTO v_min_tier_sort FROM hp_tiers WHERE id = v_reward.min_tier_id;
        IF COALESCE(v_user_tier_sort, 0) < COALESCE(v_min_tier_sort, 0) THEN
            RETURN jsonb_build_object('success', false, 'error', 'tier_too_low');
        END IF;
    END IF;
    IF v_reward.max_per_user IS NOT NULL AND v_reward.max_per_user > 0 THEN
        SELECT count(*) INTO v_user_redeem_count FROM reward_redemptions
        WHERE user_id = p_user_id AND reward_id = p_reward_id AND status <> 'rejected';
        IF v_user_redeem_count >= v_reward.max_per_user THEN
            RETURN jsonb_build_object('success', false, 'error', 'max_per_user_reached', 'limit', v_reward.max_per_user);
        END IF;
    END IF;

    SELECT count(*) INTO v_redeemed_count FROM reward_redemptions rr
    JOIN hp_transactions ht ON ht.reference_id = rr.id AND ht.reference_type = 'flash_reward_redemption'
    WHERE rr.reward_id = p_reward_id AND rr.created_at >= v_flash.window_starts_at
      AND rr.campus_id IS NOT DISTINCT FROM v_flash.campus_id;
    IF v_redeemed_count >= v_flash.quantity_limit THEN
        RETURN jsonb_build_object('success', false, 'error', 'limit_reached', 'qty', v_flash.quantity_limit);
    END IF;

    v_discounted_cost := floor(v_reward.hp_cost * (1 - v_flash.discount_pct))::INTEGER;
    v_redemption_id := gen_random_uuid();
    SELECT hp_balance INTO v_current_balance FROM profiles WHERE id = p_user_id;

    v_hp_result := public.record_hp_transaction_atomic(
        p_user_id, -v_discounted_cost, 'spend', 'active', 'flash_reward_redemption',
        'flash_reward_redemption', v_redemption_id, NULL,
        format('Flash deal: %s at %s%% off', v_reward.name, round(v_flash.discount_pct * 100)), v_flash.campus_id
    );
    IF v_hp_result ? 'error' THEN
        RETURN jsonb_build_object('success', false, 'error', v_hp_result->>'error',
            'hp_cost', v_discounted_cost, 'have', COALESCE(v_current_balance, 0));
    END IF;

    IF v_reward.stock_quantity IS NOT NULL THEN
        UPDATE rewards SET stock_quantity = stock_quantity - 1 WHERE id = p_reward_id;
    END IF;

    INSERT INTO reward_redemptions (id, user_id, reward_id, hp_cost_snapshot, status, campus_id)
    VALUES (v_redemption_id, p_user_id, p_reward_id, v_discounted_cost, 'pending', v_flash.campus_id);

    RETURN jsonb_build_object('success', true, 'redemption_id', v_redemption_id, 'hp_cost', v_discounted_cost,
        'discount_pct', v_flash.discount_pct, 'reward_name', v_reward.name, 'transaction_id', v_hp_result->>'transaction_id');
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$function$
