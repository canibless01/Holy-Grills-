CREATE FUNCTION public.hg_store_dispatch_ready(p_actor uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM profiles WHERE id=p_actor AND is_active AND role::text='super_admin') THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 RETURN to_regclass('public.delivery_batches_open_store_window_gate_uidx') IS NOT NULL
 AND EXISTS(SELECT 1 FROM pg_index WHERE indexrelid=to_regclass('public.delivery_batches_open_window_gate_uidx') AND strpos(pg_get_expr(indpred,indrelid),'store_id IS NULL')>0);
END $$;
REVOKE ALL ON FUNCTION public.hg_store_dispatch_ready(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_store_dispatch_ready(uuid) TO service_role;

CREATE FUNCTION public.hg_store_riders(p_actor uuid,p_campus uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM profiles WHERE id=p_actor AND is_active AND (role::text='super_admin' OR (role::text IN('admin','kitchen') AND campus_id=p_campus))) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('id',p.id,'full_name',coalesce(nullif(p.full_name,''),nullif(p.nickname,''),p.email::text),'store_ids',
  coalesce((SELECT jsonb_agg(m.store_id) FROM hg_internal.store_staff m JOIN stores s ON s.id=m.store_id WHERE m.user_id=p.id AND s.campus_id=p_campus),'[]')) ORDER BY p.full_name,p.id)
 FROM profiles p WHERE p.campus_id=p_campus AND p.is_active AND p.role::text='rider'),'[]');
END $$;
REVOKE ALL ON FUNCTION public.hg_store_riders(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_store_riders(uuid,uuid) TO service_role;

DO $gate$
DECLARE body text;before_text text;after_text text;
BEGIN
 SELECT pg_get_functiondef('hg_internal.guard_multi_store_activation()'::regprocedure) INTO body;
 before_text:=$old$ IF NEW.feature_name='multi_store_ordering' AND NEW.is_active THEN$old$;
 after_text:=$new$ IF NEW.feature_name='multi_store_ordering' AND NEW.is_active THEN
  IF to_regclass('public.delivery_batches_open_store_window_gate_uidx') IS NULL OR NOT EXISTS(SELECT 1 FROM pg_index WHERE indexrelid=to_regclass('public.delivery_batches_open_window_gate_uidx') AND strpos(pg_get_expr(indpred,indrelid),'store_id IS NULL')>0) THEN RAISE EXCEPTION 'HG_STORE_CUTOVER_NOT_READY' USING ERRCODE='23514';END IF;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store release guard source changed';END IF;
 EXECUTE replace(body,before_text,after_text);
END $gate$;
NOTIFY pgrst,'reload schema';

-- Revoking a rider blocks new assignment, without preventing historical batch
-- completion/cancellation/payout updates that do not change that rider.
CREATE OR REPLACE FUNCTION hg_internal.guard_store_batch() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF TG_OP='UPDATE' AND (NEW.store_id IS DISTINCT FROM OLD.store_id OR (NEW.store_id IS NOT NULL AND NEW.campus_id IS DISTINCT FROM OLD.campus_id)) THEN RAISE EXCEPTION 'HG_STORE_BATCH_IMMUTABLE' USING ERRCODE='23514';END IF;
 IF NEW.store_id IS NOT NULL THEN
  IF NEW.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM stores WHERE id=NEW.store_id AND campus_id=NEW.campus_id) THEN RAISE EXCEPTION 'HG_STORE_BATCH_MISMATCH' USING ERRCODE='23514';END IF;
  IF NEW.rider_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.rider_id IS DISTINCT FROM OLD.rider_id) AND NOT EXISTS(SELECT 1 FROM profiles p JOIN hg_internal.store_staff m ON m.user_id=p.id
    WHERE p.id=NEW.rider_id AND p.is_active AND p.role::text='rider' AND p.campus_id=NEW.campus_id AND m.store_id=NEW.store_id) THEN RAISE EXCEPTION 'HG_STORE_RIDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION hg_internal.guard_store_delivery_assignment() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s uuid;c uuid;kind text;
BEGIN
 SELECT store_id,campus_id,delivery_type INTO s,c,kind FROM orders WHERE id=NEW.order_id;
 IF kind='store_pickup' THEN RAISE EXCEPTION 'store_pickup_no_rider' USING ERRCODE='23514';END IF;
 IF s IS NULL THEN RETURN NEW;END IF;
 IF NEW.batch_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM delivery_batches b WHERE b.id=NEW.batch_id AND b.store_id=s AND b.campus_id=c) THEN RAISE EXCEPTION 'HG_STORE_BATCH_MISMATCH' USING ERRCODE='23514';END IF;
 IF TG_OP='INSERT' OR NEW.rider_id IS DISTINCT FROM OLD.rider_id OR NEW.order_id IS DISTINCT FROM OLD.order_id THEN
  IF NOT EXISTS(SELECT 1 FROM profiles p JOIN hg_internal.store_staff m ON m.user_id=p.id WHERE p.id=NEW.rider_id AND p.is_active AND p.role::text='rider' AND p.campus_id=c AND m.store_id=s) THEN RAISE EXCEPTION 'HG_STORE_RIDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_store_delivery_assignment() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_store_delivery_assignment() TO service_role;
CREATE TRIGGER store_delivery_assignment_guard BEFORE INSERT OR UPDATE OF order_id,rider_id,batch_id ON public.delivery_assignments FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_store_delivery_assignment();

-- Private, auth.uid-bound lookup avoids policy cycles between orders/items/
-- assignments. Historical own rider work remains readable after a team change.
CREATE FUNCTION hg_internal.current_user_can_read_order_store(p_order uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE actor uuid;kind text;o public.orders;
BEGIN
 actor:=auth.uid();
 SELECT p.role::text INTO kind FROM public.profiles p WHERE p.id=actor AND p.is_active;
 IF NOT FOUND THEN RETURN false;END IF;
 IF kind NOT IN('kitchen','rider') THEN RETURN true;END IF;
 SELECT * INTO o FROM public.orders WHERE id=p_order;
 IF NOT FOUND THEN RETURN false;END IF;
 IF o.store_id IS NULL THEN RETURN true;END IF;
 IF kind='rider' AND o.status::text IN('delivered','cancelled','refunded','unclaimed') AND public.hg_effective_rider(o.id)=actor THEN RETURN true;END IF;
 RETURN hg_internal.current_user_has_store(o.store_id);
END $$;
REVOKE ALL ON FUNCTION hg_internal.current_user_can_read_order_store(uuid) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION hg_internal.current_user_can_read_order_store(uuid) TO authenticated,service_role;
ALTER POLICY order_store_staff_read ON public.orders USING(hg_internal.current_user_can_read_order_store(id));
ALTER POLICY item_store_staff_read ON public.order_items USING(hg_internal.current_user_can_read_order_store(order_id));
ALTER POLICY assignment_store_staff_read ON public.delivery_assignments USING(hg_internal.current_user_can_read_order_store(order_id));
ALTER POLICY batch_store_staff_read ON public.delivery_batches
 USING(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider')
  OR ((SELECT public.hg_current_user_role())='rider' AND rider_id=(SELECT auth.uid())) OR hg_internal.current_user_has_store(store_id));
