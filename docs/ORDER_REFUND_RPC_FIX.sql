-- One transaction for the refund ledger, counters, terminal status and reusable
-- pre-preparation claims. No additional tables or financial rows are required.
CREATE OR REPLACE FUNCTION public.hg_refund_order_atomic(
    p_order_id uuid, p_actor_id uuid, p_request_key text,
    p_requested_amount numeric DEFAULT NULL, p_reason text DEFAULT NULL,
    p_customer_cancel boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $refund$
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
$refund$;
REVOKE ALL ON FUNCTION public.hg_refund_order_atomic(uuid,uuid,text,numeric,text,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_refund_order_atomic(uuid,uuid,text,numeric,text,boolean) TO service_role;
