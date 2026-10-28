-- Keep promo admission counters consistent with fully reversed purchases.
DO $migration$
DECLARE body text; marker text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND p.pronargs=38;
 body:=replace(body,'status<>''cancelled''','status NOT IN (''cancelled'',''refunded'')');
 EXECUTE body;
 SELECT pg_get_functiondef('public.hg_refund_order_atomic(uuid,uuid,text,numeric,text,boolean)'::regprocedure) INTO body;
 marker:='    v_provider_ref := ''order-refund-event:''';
 IF position(marker IN body)=0 THEN RAISE EXCEPTION 'refund_definition_changed'; END IF;
 body:=replace(body,marker,'    -- Same promo -> wallet lock order as checkout.
    PERFORM 1 FROM public.promo_codes WHERE id=v_order.promo_code_id FOR UPDATE;
'||marker);
 marker:='    v_status_changed := v_target_status IS DISTINCT FROM v_order.status;';
 IF position(marker IN body)=0 THEN RAISE EXCEPTION 'refund_definition_changed'; END IF;
 body:=replace(body,marker,'    IF v_amount=v_remaining AND v_order.status::text NOT IN (''cancelled'',''refunded'')
      AND v_target_status::text IN (''cancelled'',''refunded'') AND v_order.promo_code_id IS NOT NULL THEN
        UPDATE public.promo_codes SET used_count=greatest(0,used_count-1) WHERE id=v_order.promo_code_id;
    END IF;
'||marker);
 EXECUTE body;
END $migration$;
