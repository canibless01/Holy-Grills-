-- Keep the existing status-machine trigger and its single function signature.
CREATE OR REPLACE FUNCTION public.hg_verify_order_status_transition()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE
  v_allowed text[];
BEGIN
  IF new.status::text IN ('paid','preparing','ready','assigned','out_for_delivery','delivered','delivery_attempted','unclaimed')
     AND coalesce(new.payment_status::text,'') NOT IN ('paid','partially_refunded') THEN
    RAISE EXCEPTION 'order_payment_required_for_fulfilment' USING ERRCODE='23514';
  END IF;
  IF tg_op='INSERT' OR new.status=old.status THEN RETURN new; END IF;
  v_allowed := CASE old.status::text
    WHEN 'scheduled' THEN ARRAY['received','cancelled']
    WHEN 'received' THEN ARRAY['paid','preparing','cancelled','refunded']
    WHEN 'paid' THEN ARRAY['preparing','cancelled','refunded']
    WHEN 'preparing' THEN ARRAY['ready','cancelled','refunded']
    WHEN 'ready' THEN ARRAY['assigned','out_for_delivery','cancelled','refunded']
    WHEN 'assigned' THEN ARRAY['ready','out_for_delivery','cancelled','refunded']
    WHEN 'out_for_delivery' THEN ARRAY['delivered','delivery_attempted','refunded']
    WHEN 'delivery_attempted' THEN ARRAY['delivered','unclaimed','refunded']
    WHEN 'unclaimed' THEN ARRAY['cancelled','refunded']
    WHEN 'delivered' THEN ARRAY['refunded']
    ELSE ARRAY[]::text[]
  END;
  IF NOT (new.status::text=ANY(v_allowed)) THEN
    RAISE EXCEPTION 'Invalid order status transition: % -> %',old.status,new.status;
  END IF;
  RETURN new;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_verify_order_status_transition() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_verify_order_status_transition() TO service_role;
