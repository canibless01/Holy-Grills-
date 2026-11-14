CREATE OR REPLACE FUNCTION public.hg_verify_promo_use_limit()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_max_per_user integer; v_user_uses_count integer;
BEGIN
 SELECT max_uses_per_user INTO v_max_per_user FROM public.promo_codes WHERE id=NEW.promo_code_id FOR UPDATE;
 IF v_max_per_user IS NOT NULL AND NEW.user_id IS NOT NULL THEN
   SELECT count(*) INTO v_user_uses_count FROM public.promo_code_uses uses
   JOIN public.orders o ON o.id=uses.order_id
   WHERE uses.promo_code_id=NEW.promo_code_id AND uses.user_id=NEW.user_id
     AND uses.id IS DISTINCT FROM NEW.id AND o.status::text NOT IN ('cancelled','refunded');
   IF v_user_uses_count>=v_max_per_user THEN RAISE EXCEPTION 'promo_use_limit_reached'; END IF;
 END IF;
 RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_verify_promo_use_limit() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_verify_promo_use_limit() TO service_role;
