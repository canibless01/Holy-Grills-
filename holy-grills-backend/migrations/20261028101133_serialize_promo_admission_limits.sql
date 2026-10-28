-- Serialize global/campus promo limits at the same boundary as the debit.
DO $migration$
DECLARE body text; marker text; guard text; location integer;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND p.pronargs=38;
 IF body IS NULL OR position('    v_final_total_amount NUMERIC;' IN body)=0 THEN RAISE EXCEPTION 'order_definition_changed'; END IF;
 body:=replace(body,'    v_final_total_amount NUMERIC;','    v_promo public.promo_codes%ROWTYPE;
    v_final_total_amount NUMERIC;');
 marker:='    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) i';
 location:=position(marker IN body);
 IF location=0 THEN RAISE EXCEPTION 'order_definition_changed'; END IF;
 guard:='    IF p_promo_code_id IS NOT NULL THEN
        SELECT * INTO v_promo FROM public.promo_codes WHERE id=p_promo_code_id FOR UPDATE;
        IF NOT FOUND OR p_user_id IS NULL OR NOT v_promo.is_active
        OR (v_promo.campus_id IS NOT NULL AND v_promo.campus_id IS DISTINCT FROM p_campus_id)
        OR (v_promo.starts_at IS NOT NULL AND now()<v_promo.starts_at)
        OR (v_promo.ends_at IS NOT NULL AND now()>v_promo.ends_at)
        OR p_subtotal<coalesce(v_promo.min_order_amount,0)
        OR (v_promo.max_uses IS NOT NULL AND (SELECT count(*) FROM public.orders WHERE promo_code_id=p_promo_code_id AND status<>''cancelled'')>=v_promo.max_uses)
        OR (v_promo.max_uses_per_user IS NOT NULL AND (SELECT count(*) FROM public.orders WHERE promo_code_id=p_promo_code_id AND user_id=p_user_id AND status<>''cancelled'')>=v_promo.max_uses_per_user)
        THEN RETURN jsonb_build_object(''error'',''promo_unavailable''); END IF;
    END IF;
';
 body:=substr(body,1,location-1)||guard||substr(body,location);
 EXECUTE body;
END $migration$;
