-- Review draft only. Reuses existing claim signature and signup trigger.
-- Verified owner replay never grants HP here; delivery recovery remains idempotent.
CREATE OR REPLACE FUNCTION public.claim_guest_order(p_order_id uuid,p_claim_token uuid,p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_actor public.profiles%ROWTYPE; v_order public.orders%ROWTYPE;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN
  RAISE EXCEPTION 'guest_claim_forbidden' USING ERRCODE='42501';
 END IF;
 SELECT * INTO v_actor FROM public.profiles WHERE id=p_user_id FOR SHARE;
 IF NOT FOUND OR NOT coalesce(v_actor.is_active,false) OR v_actor.role::text<>'student' THEN
  RETURN jsonb_build_object('error','forbidden');
 END IF;
 SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','order_not_found'); END IF;
 IF v_actor.campus_id IS NULL OR v_actor.campus_id IS DISTINCT FROM v_order.campus_id THEN
  RETURN jsonb_build_object('error','campus_mismatch');
 END IF;
 IF v_order.user_id=p_user_id THEN
  RETURN jsonb_build_object('success',true,'order_id',p_order_id,'replayed',true,'status',v_order.status);
 END IF;
 IF v_order.user_id IS NOT NULL THEN RETURN jsonb_build_object('error','already_claimed'); END IF;
 IF v_order.payment_status::text NOT IN ('paid','partially_refunded','refunded') THEN
  RETURN jsonb_build_object('error','payment_pending');
 END IF;
 IF p_claim_token IS NULL OR v_order.claim_token IS NULL OR v_order.claim_token<>p_claim_token THEN
  RETURN jsonb_build_object('error','invalid_claim');
 END IF;
 UPDATE public.orders SET user_id=p_user_id,claim_token=NULL WHERE id=p_order_id;
 RETURN jsonb_build_object('success',true,'order_id',p_order_id,'replayed',false,'status',v_order.status);
END;
$function$;
REVOKE ALL ON FUNCTION public.claim_guest_order(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_guest_order(uuid,uuid,uuid) TO service_role;

-- A profile email alone is user-controlled contact data. Only the actual
-- verified Auth email may recover same-campus guest orders automatically.
CREATE OR REPLACE FUNCTION public.hg_link_guest_orders_to_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_email text; v_previous_flag text;
BEGIN
 IF NEW.role::text<>'student' OR NOT coalesce(NEW.is_active,false) OR NEW.campus_id IS NULL THEN RETURN NEW; END IF;
 SELECT email INTO v_email FROM auth.users
  WHERE id=NEW.id AND email_confirmed_at IS NOT NULL AND deleted_at IS NULL;
 IF v_email IS NULL OR lower(trim(v_email)) IS DISTINCT FROM lower(trim(NEW.email::text)) THEN RETURN NEW; END IF;
 v_previous_flag:=coalesce(current_setting('hg.linking_guest_orders',true),'');
 PERFORM set_config('hg.linking_guest_orders','on',true);
 UPDATE public.orders SET user_id=NEW.id,claim_token=NULL
  WHERE guest_email=v_email AND user_id IS NULL AND campus_id=NEW.campus_id AND payment_status::text IN ('paid','partially_refunded','refunded');
 PERFORM set_config('hg.linking_guest_orders',v_previous_flag,true);
 RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_link_guest_orders_to_user() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_link_guest_orders_to_user() TO service_role;
