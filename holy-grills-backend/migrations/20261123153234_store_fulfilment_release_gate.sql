-- Replace the temporary hard stop only with an explicit configuration check.
-- Do not enable any campus/global flag in this migration.
CREATE OR REPLACE FUNCTION hg_internal.guard_multi_store_activation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NEW.feature_name='multi_store_ordering' AND NEW.is_active THEN
  IF EXISTS(SELECT 1 FROM campuses c WHERE c.is_active AND (NEW.campus_id IS NULL OR c.id=NEW.campus_id)
    AND NOT EXISTS(SELECT 1 FROM stores s WHERE s.campus_id=c.id AND s.is_active))
  OR EXISTS(SELECT 1 FROM stores s JOIN campuses c ON c.id=s.campus_id WHERE s.is_active AND c.is_active AND (NEW.campus_id IS NULL OR c.id=NEW.campus_id)
    AND ((s.delivery_enabled AND (s.lat IS NULL OR s.lon IS NULL))
      OR NOT EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.role::text='kitchen' AND p.campus_id=s.campus_id)
      OR (s.delivery_enabled AND NOT EXISTS(SELECT 1 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=s.id AND p.is_active AND p.role::text='rider' AND p.campus_id=s.campus_id)))) THEN
   RAISE EXCEPTION 'HG_STORE_CUTOVER_NOT_READY' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION hg_internal.guard_store_batch() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF TG_OP='UPDATE' AND (NEW.store_id IS DISTINCT FROM OLD.store_id OR (NEW.store_id IS NOT NULL AND NEW.campus_id IS DISTINCT FROM OLD.campus_id)) THEN RAISE EXCEPTION 'HG_STORE_BATCH_IMMUTABLE' USING ERRCODE='23514';END IF;
 IF NEW.store_id IS NOT NULL THEN
  IF NEW.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM stores WHERE id=NEW.store_id AND campus_id=NEW.campus_id) THEN RAISE EXCEPTION 'HG_STORE_BATCH_MISMATCH' USING ERRCODE='23514';END IF;
  IF NEW.rider_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM profiles p JOIN hg_internal.store_staff m ON m.user_id=p.id
    WHERE p.id=NEW.rider_id AND p.is_active AND p.role::text='rider' AND p.campus_id=NEW.campus_id AND m.store_id=NEW.store_id) THEN RAISE EXCEPTION 'HG_STORE_RIDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 END IF;
 RETURN NEW;
END $$;

DO $pickup$
DECLARE body text;before_text text;after_text text;
BEGIN
 SELECT pg_get_functiondef('hg_internal.enforce_store_pickup_order()'::regprocedure) INTO body;
 before_text:=$old$SELECT value INTO location FROM public.system_settings WHERE key='store_pickup_location' AND campus_id=NEW.campus_id;$old$;
 after_text:=$new$IF NEW.store_id IS NULL THEN
    SELECT value INTO location FROM public.system_settings WHERE key='store_pickup_location' AND campus_id=NEW.campus_id;
   ELSE
    SELECT jsonb_build_object('name',s.name,'address',s.address,'instructions',s.instructions) INTO location FROM public.stores s
    WHERE s.id=NEW.store_id AND s.campus_id=NEW.campus_id AND s.is_active AND s.pickup_enabled;
   END IF;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Pickup store source changed';END IF;
 EXECUTE replace(body,before_text,after_text);
END $pickup$;
NOTIFY pgrst,'reload schema';
