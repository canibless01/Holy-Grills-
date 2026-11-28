DO $migration$
DECLARE body text; original text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND p.pronargs=38;
 original:='UPDATE promo_codes SET used_count = used_count + 1 WHERE id = p_promo_code_id;';
 IF body IS NULL OR position(original IN body)=0 THEN RAISE EXCEPTION 'promo_counter_definition_changed'; END IF;
 EXECUTE replace(body,original,'UPDATE public.promo_codes SET used_count=(SELECT count(*) FROM public.orders WHERE promo_code_id=p_promo_code_id AND status::text NOT IN (''cancelled'',''refunded'')) WHERE id=p_promo_code_id;');
END $migration$;
