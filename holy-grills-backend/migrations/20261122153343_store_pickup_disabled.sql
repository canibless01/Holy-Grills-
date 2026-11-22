-- Store pickup reuses order/payment/reward state. Admission stays disabled.
ALTER TABLE public.orders DROP CONSTRAINT orders_delivery_type_check;
ALTER TABLE public.orders ADD CONSTRAINT orders_delivery_type_check
 CHECK (delivery_type IN ('on_campus','off_campus','store_pickup'));

INSERT INTO public.feature_flags(feature_name,is_active,description,campus_id)
 SELECT 'store_pickup',false,'Allow configured physical-store collection at zero delivery fee. Preparation stays unchanged.',NULL
 WHERE NOT EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name='store_pickup' AND campus_id IS NULL)
 ON CONFLICT DO NOTHING;

DO $patch$
DECLARE body text; before_text text;
BEGIN
 SELECT pg_get_functiondef('public.hg_verify_order_status_transition()'::regprocedure) INTO body;
 before_text := 'WHEN ''ready'' THEN ARRAY[''assigned'',''out_for_delivery'',''cancelled'',''refunded'']';
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Unexpected order state-machine source'; END IF;
 EXECUTE replace(body,before_text,'WHEN ''ready'' THEN CASE WHEN NEW.delivery_type=''store_pickup'' THEN ARRAY[''delivered'',''cancelled'',''refunded''] ELSE ARRAY[''assigned'',''out_for_delivery'',''cancelled'',''refunded''] END');
 SELECT pg_get_functiondef('public.hg_protect_order_columns()'::regprocedure) INTO body;
 before_text := 'hg_current_user_role()::text=''kitchen'' and new.status::text not in (''preparing'',''ready'')';
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Unexpected kitchen order-column guard source'; END IF;
 EXECUTE replace(body,before_text,before_text||' and not (old.delivery_type=''store_pickup'' and old.status::text=''ready'' and new.status::text=''delivered'')');
END
$patch$;

CREATE OR REPLACE FUNCTION hg_internal.enforce_store_pickup_order()
 RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $body$
DECLARE enabled boolean; location jsonb;
BEGIN
 IF TG_TABLE_NAME='delivery_assignments' THEN
   IF EXISTS(SELECT 1 FROM public.orders WHERE id=NEW.order_id AND delivery_type='store_pickup') THEN
     RAISE EXCEPTION 'store_pickup_no_rider' USING ERRCODE='23514';
   END IF;
   RETURN NEW;
 END IF;
 IF TG_OP='UPDATE' AND NEW.delivery_type IS DISTINCT FROM OLD.delivery_type
    AND (NEW.delivery_type='store_pickup' OR OLD.delivery_type='store_pickup') THEN
   RAISE EXCEPTION 'store_pickup_mode_immutable' USING ERRCODE='23514';
 END IF;
 IF NEW.delivery_type IS DISTINCT FROM 'store_pickup' THEN RETURN NEW; END IF;
 IF NEW.batch_id IS NOT NULL OR NEW.status::text IN ('assigned','out_for_delivery','delivery_attempted','unclaimed') THEN
   RAISE EXCEPTION 'store_pickup_no_rider' USING ERRCODE='23514';
 END IF;
 IF NEW.delivery_fee IS DISTINCT FROM 0 OR NEW.delivery_location_id IS NOT NULL
    OR NEW.delivery_location_lat IS NOT NULL OR NEW.delivery_location_lon IS NOT NULL THEN
   RAISE EXCEPTION 'store_pickup_invalid_delivery' USING ERRCODE='23514';
 END IF;
 IF TG_OP='INSERT' THEN
   SELECT coalesce((SELECT is_active FROM public.feature_flags WHERE feature_name='store_pickup' AND campus_id=NEW.campus_id),
                   (SELECT is_active FROM public.feature_flags WHERE feature_name='store_pickup' AND campus_id IS NULL),false) INTO enabled;
   SELECT value INTO location FROM public.system_settings WHERE key='store_pickup_location' AND campus_id=NEW.campus_id;
   IF NOT enabled OR location IS NULL OR jsonb_typeof(location->'address') IS DISTINCT FROM 'string'
      OR jsonb_typeof(location->'name') IS DISTINCT FROM 'string' OR coalesce(trim(location->>'address'),'')=''
      OR coalesce(trim(location->>'name'),'')='' THEN
     RAISE EXCEPTION 'store_pickup_unavailable' USING ERRCODE='23514';
   END IF;
   IF NEW.delivery_address_snapshot->>'line1' IS DISTINCT FROM location->>'address'
      OR NEW.delivery_address_snapshot->>'location_name' IS DISTINCT FROM location->>'name' THEN
     RAISE EXCEPTION 'store_pickup_location_changed' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END
$body$;
REVOKE ALL ON FUNCTION hg_internal.enforce_store_pickup_order() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.enforce_store_pickup_order() TO service_role;
CREATE TRIGGER zz_store_pickup_order_guard BEFORE INSERT OR UPDATE ON public.orders
 FOR EACH ROW EXECUTE FUNCTION hg_internal.enforce_store_pickup_order();
CREATE TRIGGER zz_store_pickup_assignment_guard BEFORE INSERT OR UPDATE ON public.delivery_assignments
 FOR EACH ROW EXECUTE FUNCTION hg_internal.enforce_store_pickup_order();
