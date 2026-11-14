-- Review draft: replace the dormant helper and stage paid READY orders without
-- assigning a rider. Uses existing tables; no backfill or cleanup is performed.
CREATE OR REPLACE FUNCTION public.hg_auto_assign_order_to_batch(p_order_id uuid)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE
    v_order public.orders%ROWTYPE;
    v_gate_id uuid;
    v_gate_name text;
    v_batch_id uuid;
BEGIN
    -- Lock order before advisory/batch, matching manual and rider operations.
    -- Never lock another order while holding the group lock.
    SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
    IF NOT FOUND OR v_order.status::text<>'ready'
       OR v_order.payment_status::text NOT IN ('paid','partially_refunded') THEN RETURN NULL; END IF;
    IF v_order.batch_id IS NOT NULL THEN RETURN v_order.batch_id; END IF;
    IF v_order.campus_id IS NULL OR v_order.delivery_window_id IS NULL
       OR v_order.delivery_location_id IS NULL
       OR EXISTS(SELECT 1 FROM public.delivery_assignments WHERE order_id=p_order_id)
       OR NOT EXISTS(SELECT 1 FROM public.delivery_windows WHERE id=v_order.delivery_window_id AND campus_id=v_order.campus_id)
       THEN RETURN NULL; END IF;
    IF v_order.delivery_type::text='off_campus' THEN
        v_gate_id:=v_order.delivery_location_id;
    ELSIF v_order.delivery_type::text='on_campus' THEN
        SELECT gate_id INTO v_gate_id FROM public.hostels
        WHERE id=v_order.delivery_location_id AND is_active
          AND (campus_id=v_order.campus_id OR campus_id IS NULL);
    END IF;
    SELECT name INTO v_gate_name FROM public.gates WHERE id=v_gate_id AND is_active
      AND (campus_id=v_order.campus_id OR campus_id IS NULL);
    IF NOT FOUND THEN RETURN NULL; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('delivery-stage:'||v_order.campus_id::text||':'||v_gate_id::text||':'||v_order.delivery_window_id::text,0));
    -- A concurrent manual assignment may have sealed the candidate while this
    -- SELECT waited. READ COMMITTED rechecks these predicates after row locking.
    SELECT id INTO v_batch_id FROM public.delivery_batches
    WHERE campus_id=v_order.campus_id AND gate_id=v_gate_id
      AND delivery_window_id=v_order.delivery_window_id
      AND window_id=v_order.delivery_window_id AND status='open' AND rider_id IS NULL
    ORDER BY created_at,id LIMIT 1 FOR UPDATE;
    IF v_batch_id IS NULL THEN
        INSERT INTO public.delivery_batches(window_id,delivery_window_id,gate_id,zone,status,campus_id)
        VALUES(v_order.delivery_window_id,v_order.delivery_window_id,v_gate_id,coalesce(v_gate_name,''),'open',v_order.campus_id)
        RETURNING id INTO v_batch_id;
    END IF;
    -- Staging leaves status READY, assigned_at empty, and no rider override.
    UPDATE public.orders SET batch_id=v_batch_id WHERE id=p_order_id;
    RETURN v_batch_id;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_auto_assign_order_to_batch(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_auto_assign_order_to_batch(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_stage_ready_order_groups()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE v_id uuid;
BEGIN
    -- Transition tables run after the kitchen statement has locked all affected
    -- orders. Sort group locks consistently for bulk operations. Nested helper
    -- batch_id writes and cancellation assigned->ready releases are ignored.
    IF TG_OP='INSERT' THEN
        FOR v_id IN
            SELECT n.id FROM hg_stage_new n
            LEFT JOIN public.hostels h ON n.delivery_type::text='on_campus' AND h.id=n.delivery_location_id
              AND (h.campus_id=n.campus_id OR h.campus_id IS NULL)
            WHERE n.status::text='ready' AND n.batch_id IS NULL
              AND n.payment_status::text IN ('paid','partially_refunded')
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    ELSE
        FOR v_id IN
            SELECT n.id FROM hg_stage_new n JOIN hg_stage_old o USING(id)
            LEFT JOIN public.hostels h ON n.delivery_type::text='on_campus' AND h.id=n.delivery_location_id
              AND (h.campus_id=n.campus_id OR h.campus_id IS NULL)
            WHERE n.status::text='ready' AND o.status::text='preparing'
              AND o.batch_id IS NULL AND n.batch_id IS NULL
              AND n.payment_status::text IN ('paid','partially_refunded')
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    END IF;
    RETURN NULL;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_stage_ready_order_groups() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_stage_ready_order_groups() TO service_role;
DROP TRIGGER IF EXISTS trg_orders_stage_ready_insert ON public.orders;
CREATE TRIGGER trg_orders_stage_ready_insert AFTER INSERT ON public.orders
REFERENCING NEW TABLE AS hg_stage_new FOR EACH STATEMENT
EXECUTE FUNCTION public.hg_stage_ready_order_groups();
DROP TRIGGER IF EXISTS trg_orders_stage_ready_update ON public.orders;
CREATE TRIGGER trg_orders_stage_ready_update AFTER UPDATE ON public.orders
REFERENCING OLD TABLE AS hg_stage_old NEW TABLE AS hg_stage_new FOR EACH STATEMENT
EXECUTE FUNCTION public.hg_stage_ready_order_groups();
