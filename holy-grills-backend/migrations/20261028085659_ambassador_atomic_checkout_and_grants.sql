-- Existing ledgers only. Service-only atomic financial boundaries.
-- Grant ledger and benefit commit together. A failed award leaves neither.
CREATE OR REPLACE FUNCTION public.hg_issue_ambassador_grant_atomic(
 p_actor_id uuid,p_ambassador_id uuid,p_category text,p_amount numeric,p_month text,p_reason text,
 p_validity_days integer,p_uses integer,p_source text,p_claim_id uuid,p_override boolean,p_intent text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; target public.profiles%ROWTYPE;
 grant_row public.ambassador_grants%ROWTYPE; discount public.ambassador_meal_discounts%ROWTYPE;
 hp jsonb; credit jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor_id AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 PERFORM 1 FROM public.wallets WHERE user_id=p_ambassador_id FOR UPDATE;
 SELECT * INTO target FROM public.profiles WHERE id=p_ambassador_id AND is_active FOR UPDATE;
 IF NOT FOUND OR (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM target.campus_id)
 OR NOT EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=p_ambassador_id AND status='active')
 THEN RAISE EXCEPTION 'ambassador_forbidden'; END IF;
 IF p_amount IS NULL OR p_amount::text IN ('NaN','Infinity','-Infinity') OR p_amount<=0 OR p_amount>1000000
 OR p_category NOT IN ('hp','free_side','meal_discount') OR p_month !~ '^\d{4}-(0[1-9]|1[0-2])$'
 OR nullif(btrim(p_reason),'') IS NULL OR length(p_reason)>500 OR nullif(p_intent,'') IS NULL
 OR p_validity_days IS NULL OR p_validity_days NOT BETWEEN 1 AND 365 OR p_uses IS NULL OR p_uses NOT BETWEEN 1 AND 100
 OR (p_category IN ('hp','free_side') AND p_amount<>trunc(p_amount))
 OR (p_category='free_side' AND p_amount>20) THEN RAISE EXCEPTION 'ambassador_grant_invalid'; END IF;
 SELECT * INTO grant_row FROM public.ambassador_grants WHERE idempotency_key=p_intent;
 IF FOUND THEN
   IF grant_row.ambassador_id<>p_ambassador_id OR grant_row.reward_category<>p_category OR grant_row.amount<>p_amount
   OR grant_row.reason<>p_reason OR grant_row.issued_by<>p_actor_id OR grant_row.month<>p_month
   OR grant_row.validity_days IS DISTINCT FROM p_validity_days OR grant_row.uses_count<>p_uses
   OR grant_row.source IS DISTINCT FROM p_source OR grant_row.milestone_claim_id IS DISTINCT FROM p_claim_id
   OR grant_row.duplicate_override IS DISTINCT FROM p_override THEN RAISE EXCEPTION 'ambassador_intent_conflict'; END IF;
   RETURN to_jsonb(grant_row)||jsonb_build_object('idempotent',true);
 END IF;
 IF NOT p_override AND EXISTS(SELECT 1 FROM public.ambassador_grants WHERE ambassador_id=p_ambassador_id
   AND month=p_month AND reward_category=p_category AND NOT duplicate_override) THEN
   RETURN jsonb_build_object('error','duplicate_monthly_grant'); END IF;
 INSERT INTO public.ambassador_grants(ambassador_id,month,reward_category,amount,uses_count,validity_days,
   reason,source,milestone_claim_id,duplicate_override,idempotency_key,issued_by)
 VALUES(p_ambassador_id,p_month,p_category,p_amount,p_uses,p_validity_days,p_reason,p_source,p_claim_id,p_override,p_intent)
 RETURNING * INTO grant_row;
 IF p_category='hp' THEN
   hp:=public.record_hp_transaction_atomic(p_ambassador_id,p_amount::integer,'earn','active',
      'ambassador_grant','ambassador_grant',grant_row.id,p_actor_id,p_reason,target.campus_id);
   IF hp ? 'error' THEN RAISE EXCEPTION 'ambassador_award_failed'; END IF;
   UPDATE public.ambassador_grants SET hp_transaction_id=(SELECT id FROM public.hp_transactions
     WHERE user_id=p_ambassador_id AND reference_id=grant_row.id AND reference_type='ambassador_grant' LIMIT 1)
     WHERE id=grant_row.id RETURNING * INTO grant_row;
 ELSIF p_category='free_side' THEN
   credit:=public.hg_grant_free_sides_atomic(p_actor_id,p_ambassador_id,grant_row.id,p_amount::integer,p_validity_days,p_reason);
   IF credit ? 'error' OR credit->>'credit_id' IS NULL THEN RAISE EXCEPTION 'ambassador_award_failed'; END IF;
   UPDATE public.ambassador_grants SET free_side_grant_id=(credit->>'credit_id')::uuid,
     expires_at=(credit->>'expires_at')::timestamptz WHERE id=grant_row.id RETURNING * INTO grant_row;
 ELSE
   discount:=public.hg_grant_ambassador_meal_discount(p_actor_id,p_ambassador_id,p_amount,p_uses,p_validity_days,grant_row.id,p_reason);
   SELECT * INTO grant_row FROM public.ambassador_grants WHERE id=grant_row.id;
 END IF;
 IF p_claim_id IS NOT NULL THEN
   UPDATE public.ambassador_milestone_claims SET status='issued',grant_id=grant_row.id,
     decided_by=p_actor_id,decided_at=now() WHERE id=p_claim_id AND ambassador_id=p_ambassador_id;
   IF NOT FOUND THEN RAISE EXCEPTION 'ambassador_claim_invalid'; END IF;
 END IF;
 RETURN to_jsonb(grant_row)||jsonb_build_object('idempotent',false);
END; $$;
REVOKE ALL ON FUNCTION public.hg_issue_ambassador_grant_atomic(uuid,uuid,text,numeric,text,text,integer,integer,text,uuid,boolean,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_issue_ambassador_grant_atomic(uuid,uuid,text,numeric,text,text,integer,integer,text,uuid,boolean,text) TO service_role;

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
        VALUES (p_promo_code_id, p_user_id, v_order_id, greatest(0,p_discount_amount-coalesce(p_squad_discount_amount,0)-v_lock_discount_applied), NOW());
        UPDATE promo_codes SET used_count = used_count + 1 WHERE id = p_promo_code_id;
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

  IF p_visitor_user_id=v_ambassador THEN RETURN jsonb_build_object('attributed',false,'reason','self_click'); END IF;

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

  IF v_adopted=0 THEN RETURN jsonb_build_object('adopted_clicks',0,'attributed',false); END IF;

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
     OR COALESCE(v_order.payment_status, '') NOT IN ('paid','partially_refunded') THEN
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

NOTIFY pgrst,'reload schema';
