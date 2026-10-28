-- Track only the promo portion of combined checkout discounts.
DO $migration$
DECLARE body text; original text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND p.pronargs=38;
 original:='greatest(0,p_discount_amount-coalesce(p_squad_discount_amount,0)-v_lock_discount_applied)';
 IF body IS NULL OR position(original IN body)=0 THEN RAISE EXCEPTION 'order_promo_definition_changed'; END IF;
 EXECUTE replace(body,original,'coalesce((p_items->0->>''_promo_discount_amount'')::numeric,greatest(0,p_discount_amount-coalesce(p_squad_discount_amount,0)-v_lock_discount_applied-coalesce((p_items->0->''_ambassador_meal_discount''->>''amount'')::numeric,0)))');
END $migration$;
