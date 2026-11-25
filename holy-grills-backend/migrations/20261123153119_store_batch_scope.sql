-- Store ownership narrows staff access and batching; campus schedules stay shared.
CREATE FUNCTION hg_internal.actor_has_store(p_actor uuid,p_store uuid) RETURNS boolean
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM profiles p JOIN stores s ON s.id=p_store WHERE p.id=p_actor AND p.is_active
 AND (p.role::text='super_admin' OR (p.campus_id=s.campus_id AND (p.role::text='admin' OR
 (p.role::text IN('kitchen','rider') AND EXISTS(SELECT 1 FROM hg_internal.store_staff m WHERE m.store_id=s.id AND m.user_id=p.id))))));
$$;
REVOKE ALL ON FUNCTION hg_internal.actor_has_store(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.actor_has_store(uuid,uuid) TO service_role;
CREATE FUNCTION public.hg_staff_has_store(p_actor uuid,p_store uuid) RETURNS boolean
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$SELECT hg_internal.actor_has_store(p_actor,p_store);$$;
REVOKE ALL ON FUNCTION public.hg_staff_has_store(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_staff_has_store(uuid,uuid) TO service_role;

-- RLS must read a private membership without granting browser SELECT on it.
-- Actor identity is always auth.uid(); no caller-selected user is accepted.
CREATE FUNCTION hg_internal.current_user_has_store(p_store uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.profiles p JOIN public.stores s ON s.id=p_store
 WHERE p.id=(SELECT auth.uid()) AND p.is_active AND
 (p.role::text='super_admin' OR (p.campus_id=s.campus_id AND (p.role::text='admin' OR
 (p.role::text IN('kitchen','rider') AND EXISTS(SELECT 1 FROM hg_internal.store_staff m WHERE m.store_id=s.id AND m.user_id=p.id))))));
$$;
REVOKE ALL ON FUNCTION hg_internal.current_user_has_store(uuid) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION hg_internal.current_user_has_store(uuid) TO authenticated,service_role;
CREATE POLICY order_store_staff_read ON public.orders AS RESTRICTIVE FOR SELECT TO authenticated
 USING(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id));
CREATE POLICY order_store_staff_write ON public.orders AS RESTRICTIVE FOR UPDATE TO authenticated
 USING(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id))
 WITH CHECK(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id));
CREATE POLICY batch_store_staff_read ON public.delivery_batches AS RESTRICTIVE FOR SELECT TO authenticated
 USING(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id));

DO $scope$
DECLARE body text;before_text text;after_text text;
BEGIN
 SELECT pg_get_functiondef('public.hg_auto_assign_order_to_batch(uuid)'::regprocedure) INTO body;
 before_text:=$old$'delivery-stage:'||v_order.campus_id::text||':'||v_gate_id::text$old$;
 after_text:=$new$'delivery-stage:'||v_order.campus_id::text||':'||coalesce(v_order.store_id::text,'legacy')||':'||v_gate_id::text$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_auto_assign_order_to_batch';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$WHERE campus_id=v_order.campus_id AND gate_id=v_gate_id$old$;
 after_text:=$new$WHERE campus_id=v_order.campus_id AND store_id IS NOT DISTINCT FROM v_order.store_id AND gate_id=v_gate_id$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_auto_assign_order_to_batch';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$INSERT INTO public.delivery_batches(window_id,delivery_window_id,gate_id,zone,status,campus_id,delivery_date)$old$;
 after_text:=$new$INSERT INTO public.delivery_batches(window_id,delivery_window_id,gate_id,zone,status,campus_id,delivery_date,store_id)$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_auto_assign_order_to_batch';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$'open',v_order.campus_id,v_delivery_date)$old$;
 after_text:=$new$'open',v_order.campus_id,v_delivery_date,v_order.store_id)$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_auto_assign_order_to_batch';END IF;
 body:=replace(body,before_text,after_text);
 EXECUTE body;
END $scope$;

DO $scope$
DECLARE body text;before_text text;after_text text;
BEGIN
 SELECT pg_get_functiondef('public.hg_manage_delivery_batch_atomic(uuid,text,uuid,jsonb)'::regprocedure) INTO body;
 before_text:=$old$    v_gate_count integer;$old$;
 after_text:=$new$    v_gate_count integer;
    v_store_id uuid;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$        IF v_count<>cardinality(v_ids) THEN RAISE EXCEPTION 'batch_not_found' USING ERRCODE='P0002'; END IF;$old$;
 after_text:=$new$        IF v_count<>cardinality(v_ids) THEN RAISE EXCEPTION 'batch_not_found' USING ERRCODE='P0002'; END IF;
        IF (SELECT count(DISTINCT coalesce(store_id::text,'legacy')) FROM public.orders WHERE id=ANY(v_ids))<>1 THEN RAISE EXCEPTION 'batch_conflict';END IF;
        SELECT store_id INTO v_store_id FROM public.orders WHERE id=ANY(v_ids) ORDER BY id LIMIT 1;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$        v_campus_id := v_batch.campus_id;$old$;
 after_text:=$new$        v_campus_id := v_batch.campus_id;
        v_store_id := v_batch.store_id;
        IF v_actor.role::text='kitchen' AND v_store_id IS NOT NULL AND NOT hg_internal.actor_has_store(p_actor_id,v_store_id) THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501';END IF;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$        IF NOT FOUND OR v_rider.campus_id IS DISTINCT FROM v_campus_id THEN RAISE EXCEPTION 'batch_rider_invalid'; END IF;$old$;
 after_text:=$new$        IF NOT FOUND OR v_rider.campus_id IS DISTINCT FROM v_campus_id THEN RAISE EXCEPTION 'batch_rider_invalid'; END IF;
        IF v_store_id IS NOT NULL AND NOT hg_internal.actor_has_store(v_rider_id,v_store_id) THEN RAISE EXCEPTION 'batch_rider_invalid';END IF;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$INSERT INTO public.delivery_batches(id,window_id,delivery_window_id,rider_id,zone,status,campus_id,notes,gate_id,delivery_date)$old$;
 after_text:=$new$INSERT INTO public.delivery_batches(id,window_id,delivery_window_id,rider_id,zone,status,campus_id,notes,gate_id,delivery_date,store_id)$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 before_text:=$old$FROM public.orders o WHERE o.id=ANY(v_ids) LIMIT 1)) RETURNING * INTO v_result;$old$;
 after_text:=$new$FROM public.orders o WHERE o.id=ANY(v_ids) LIMIT 1),v_store_id) RETURNING * INTO v_result;$new$;
 IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Store scope source changed: hg_manage_delivery_batch_atomic';END IF;
 body:=replace(body,before_text,after_text);
 EXECUTE body;
END $scope$;

CREATE POLICY item_store_staff_read ON public.order_items AS RESTRICTIVE FOR SELECT TO authenticated
 USING((SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR EXISTS(SELECT 1 FROM public.orders o WHERE o.id=order_id));
CREATE POLICY assignment_store_staff_read ON public.delivery_assignments AS RESTRICTIVE FOR SELECT TO authenticated
 USING((SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR EXISTS(SELECT 1 FROM public.orders o WHERE o.id=order_id));
CREATE POLICY batch_store_staff_write ON public.delivery_batches AS RESTRICTIVE FOR UPDATE TO authenticated
 USING(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id))
 WITH CHECK(store_id IS NULL OR (SELECT public.hg_current_user_role()) NOT IN('kitchen','rider') OR hg_internal.current_user_has_store(store_id));

CREATE FUNCTION hg_internal.guard_store_batch() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF TG_OP='UPDATE' AND (NEW.store_id IS DISTINCT FROM OLD.store_id OR (NEW.store_id IS NOT NULL AND NEW.campus_id IS DISTINCT FROM OLD.campus_id)) THEN RAISE EXCEPTION 'HG_STORE_BATCH_IMMUTABLE' USING ERRCODE='23514';END IF;
 IF NEW.store_id IS NOT NULL THEN
  IF NEW.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM stores WHERE id=NEW.store_id AND campus_id=NEW.campus_id) THEN RAISE EXCEPTION 'HG_STORE_BATCH_MISMATCH' USING ERRCODE='23514';END IF;
  IF NEW.rider_id IS NOT NULL AND NOT hg_internal.actor_has_store(NEW.rider_id,NEW.store_id) THEN RAISE EXCEPTION 'HG_STORE_RIDER_UNAVAILABLE' USING ERRCODE='23514';END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_store_batch() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_store_batch() TO service_role;
CREATE TRIGGER store_batch_guard BEFORE INSERT OR UPDATE ON public.delivery_batches FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_store_batch();

CREATE FUNCTION hg_internal.guard_store_order_batch() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NEW.batch_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM delivery_batches b WHERE b.id=NEW.batch_id AND b.store_id IS NOT DISTINCT FROM NEW.store_id AND b.campus_id IS NOT DISTINCT FROM NEW.campus_id) THEN RAISE EXCEPTION 'HG_STORE_BATCH_MISMATCH' USING ERRCODE='23514';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_store_order_batch() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_store_order_batch() TO service_role;
CREATE TRIGGER store_order_batch_guard BEFORE INSERT OR UPDATE OF batch_id ON public.orders FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_store_order_batch();
NOTIFY pgrst,'reload schema';

CREATE FUNCTION public.hg_actor_stores(p_actor uuid,p_campus uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN('kitchen','rider','admin','super_admin') OR (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM p_campus) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('id',s.id,'campus_id',s.campus_id,'name',s.name,'is_active',s.is_active) ORDER BY s.name,s.id)
 FROM stores s WHERE (p_campus IS NULL OR s.campus_id=p_campus) AND hg_internal.actor_has_store(p_actor,s.id)),'[]');
END $$;
REVOKE ALL ON FUNCTION public.hg_actor_stores(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_actor_stores(uuid,uuid) TO service_role;
