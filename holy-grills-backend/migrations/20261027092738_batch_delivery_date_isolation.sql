-- Separate repeating delivery-window occurrences without new tables, columns or backfills.
CREATE OR REPLACE FUNCTION public.hg_auto_assign_order_to_batch(p_order_id uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_order public.orders%ROWTYPE;
    v_gate_id uuid;
    v_gate_name text;
    v_batch_id uuid;
    v_delivery_date date;
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
    v_delivery_date := (CASE WHEN v_order.is_scheduled THEN v_order.scheduled_for
        ELSE v_order.created_at END AT TIME ZONE 'Africa/Lagos')::date;
    IF v_delivery_date IS NULL THEN RETURN NULL; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('delivery-stage:'||v_order.campus_id::text||':'||v_gate_id::text||':'||v_order.delivery_window_id::text||':'||v_delivery_date::text,0));
    -- A concurrent manual assignment may have sealed the candidate while this
    -- SELECT waited. READ COMMITTED rechecks these predicates after row locking.
    SELECT b.id INTO v_batch_id FROM public.delivery_batches b
    WHERE campus_id=v_order.campus_id AND gate_id=v_gate_id
      AND delivery_window_id=v_order.delivery_window_id
      AND window_id=v_order.delivery_window_id AND status='open' AND rider_id IS NULL
      -- A weekly window UUID is reused across delivery dates. Infer the date
      -- from existing membership; never reuse an empty or mixed-date group.
      AND EXISTS(SELECT 1 FROM public.orders o WHERE o.batch_id=b.id)
      AND NOT EXISTS(SELECT 1 FROM public.orders o WHERE o.batch_id=b.id
        AND (CASE WHEN o.is_scheduled THEN o.scheduled_for ELSE o.created_at END
             AT TIME ZONE 'Africa/Lagos')::date IS DISTINCT FROM v_delivery_date)
    ORDER BY b.created_at,b.id LIMIT 1 FOR UPDATE OF b;
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
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,(CASE WHEN n.is_scheduled THEN n.scheduled_for ELSE n.created_at END AT TIME ZONE 'Africa/Lagos')::date,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    ELSE
        FOR v_id IN
            SELECT n.id FROM hg_stage_new n JOIN hg_stage_old o USING(id)
            LEFT JOIN public.hostels h ON n.delivery_type::text='on_campus' AND h.id=n.delivery_location_id
              AND (h.campus_id=n.campus_id OR h.campus_id IS NULL)
            WHERE n.status::text='ready' AND o.status::text='preparing'
              AND o.batch_id IS NULL AND n.batch_id IS NULL
              AND n.payment_status::text IN ('paid','partially_refunded')
            ORDER BY n.campus_id,CASE WHEN n.delivery_type::text='off_campus' THEN n.delivery_location_id ELSE h.gate_id END,n.delivery_window_id,(CASE WHEN n.is_scheduled THEN n.scheduled_for ELSE n.created_at END AT TIME ZONE 'Africa/Lagos')::date,n.id
        LOOP PERFORM public.hg_auto_assign_order_to_batch(v_id); END LOOP;
    END IF;
    RETURN NULL;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_stage_ready_order_groups() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_stage_ready_order_groups() TO service_role;

CREATE OR REPLACE FUNCTION public.hg_manage_delivery_batch_atomic(p_actor_id uuid, p_action text, p_batch_id uuid, p_body jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
    v_actor public.profiles%ROWTYPE;
    v_batch public.delivery_batches%ROWTYPE;
    v_result public.delivery_batches%ROWTYPE;
    v_window public.delivery_windows%ROWTYPE;
    v_rider public.profiles%ROWTYPE;
    v_ids uuid[] := ARRAY[]::uuid[];
    v_all_ids uuid[] := ARRAY[]::uuid[];
    v_current_ids uuid[] := ARRAY[]::uuid[];
    v_newly_assigned uuid[] := ARRAY[]::uuid[];
    v_target_id uuid;
    v_rider_id uuid;
    v_window_id uuid;
    v_campus_id uuid;
    v_zone text;
    v_status text;
    v_count integer;
    v_gate_id uuid;
    v_gate_count integer;
    v_missing_gates integer;
BEGIN
    IF coalesce(auth.role(),'') <> 'service_role' THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
    SELECT * INTO v_actor FROM public.profiles WHERE id=p_actor_id AND is_active;
    IF NOT FOUND OR v_actor.role::text NOT IN ('admin','super_admin') THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
    IF p_action IS NULL OR p_action NOT IN ('create','update','cancel','split') OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'batch_invalid'; END IF;
    IF p_body ? 'zone' AND (jsonb_typeof(p_body->'zone')<>'string' OR length(p_body->>'zone')>100) THEN RAISE EXCEPTION 'batch_invalid'; END IF;
    IF p_body ? 'notes' AND jsonb_typeof(p_body->'notes') NOT IN ('string','null') THEN RAISE EXCEPTION 'batch_invalid'; END IF;
    IF length(coalesce(p_body->>'notes',''))>500 THEN RAISE EXCEPTION 'batch_invalid'; END IF;
    IF p_action IN ('create','split') THEN
        v_target_id := coalesce((p_body->>'idempotency_key')::uuid,gen_random_uuid());
        PERFORM pg_advisory_xact_lock(hashtextextended('delivery-batch-intent:'||v_target_id::text,0));
        -- Retrying a saved create/split intent returns the existing batch even
        -- after its rider has picked up an order. It never reassigns it again.
        SELECT * INTO v_result FROM public.delivery_batches WHERE id=v_target_id;
        IF FOUND THEN
            IF v_actor.role::text<>'super_admin' AND v_actor.campus_id IS DISTINCT FROM v_result.campus_id THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
            RETURN to_jsonb(v_result)||jsonb_build_object('replayed',true,'orders_assigned',0,'orders_failed','[]'::jsonb,'notify_rider',false);
        END IF;
        IF jsonb_typeof(p_body->'order_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(p_body->'order_ids') NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'batch_invalid'; END IF;
        SELECT array_agg(id ORDER BY id) INTO v_ids FROM (SELECT DISTINCT value::uuid id FROM jsonb_array_elements_text(p_body->'order_ids')) s;
        IF cardinality(v_ids)<>jsonb_array_length(p_body->'order_ids') THEN RAISE EXCEPTION 'batch_invalid'; END IF;
        v_rider_id := (p_body->>'rider_id')::uuid;
        v_zone := trim(coalesce(p_body->>'zone',''));
        IF v_rider_id IS NULL THEN RAISE EXCEPTION 'batch_invalid'; END IF;
    END IF;
    IF p_action='create' THEN
        v_window_id := (p_body->>'window_id')::uuid;
        SELECT * INTO v_window FROM public.delivery_windows WHERE id=v_window_id;
        IF NOT FOUND OR v_window.campus_id IS NULL THEN RAISE EXCEPTION 'batch_not_found' USING ERRCODE='P0002'; END IF;
        v_campus_id := v_window.campus_id;
        IF v_actor.role::text<>'super_admin' AND v_actor.campus_id IS DISTINCT FROM v_campus_id THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
        -- All batch mutations lock orders before the batch, matching the
        -- existing rider progression trigger's order -> batch lock sequence.
        PERFORM 1 FROM public.orders WHERE id=ANY(v_ids) ORDER BY id FOR UPDATE;
        SELECT count(*) INTO v_count FROM public.orders WHERE id=ANY(v_ids);
        IF v_count<>cardinality(v_ids) THEN RAISE EXCEPTION 'batch_not_found' USING ERRCODE='P0002'; END IF;
        IF EXISTS(SELECT 1 FROM public.orders WHERE id=ANY(v_ids) AND
            (campus_id IS DISTINCT FROM v_campus_id OR status::text<>'ready' OR batch_id IS NOT NULL
             OR payment_status::text NOT IN ('paid','partially_refunded')
             OR (delivery_window_id IS NOT NULL AND delivery_window_id IS DISTINCT FROM v_window_id))) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
    ELSE
        SELECT * INTO v_batch FROM public.delivery_batches WHERE id=p_batch_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'batch_not_found' USING ERRCODE='P0002'; END IF;
        v_campus_id := v_batch.campus_id;
        IF v_campus_id IS NULL OR (v_actor.role::text<>'super_admin' AND v_actor.campus_id IS DISTINCT FROM v_campus_id) THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
        SELECT coalesce(array_agg(id ORDER BY id),ARRAY[]::uuid[]) INTO v_all_ids FROM public.orders WHERE batch_id=p_batch_id;
        PERFORM 1 FROM public.orders WHERE id=ANY(v_all_ids) ORDER BY id FOR UPDATE;
        SELECT * INTO v_batch FROM public.delivery_batches WHERE id=p_batch_id FOR UPDATE;
        SELECT coalesce(array_agg(id ORDER BY id),ARRAY[]::uuid[]) INTO v_current_ids FROM public.orders WHERE batch_id=p_batch_id;
        IF v_current_ids IS DISTINCT FROM v_all_ids THEN RAISE EXCEPTION 'batch_conflict'; END IF;
        IF p_action='cancel' AND v_batch.status='cancelled' THEN RETURN jsonb_build_object('id',p_batch_id,'batch_id',p_batch_id,'status','cancelled','orders_unassigned',0,'replayed',true); END IF;
        IF p_action IN ('cancel','split') AND v_batch.status NOT IN ('open','assigned','in_progress') THEN RAISE EXCEPTION 'batch_conflict'; END IF;
        IF EXISTS(SELECT 1 FROM public.orders WHERE batch_id=p_batch_id AND campus_id IS DISTINCT FROM v_campus_id) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
        IF p_action='cancel' THEN
            IF EXISTS(SELECT 1 FROM public.orders WHERE batch_id=p_batch_id AND status::text NOT IN ('ready','assigned')) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
            SELECT coalesce(array_agg(id ORDER BY id),ARRAY[]::uuid[]) INTO v_newly_assigned
              FROM public.orders WHERE id=ANY(v_all_ids) AND status::text='assigned';
            DELETE FROM public.delivery_assignments WHERE order_id=ANY(v_all_ids);
            UPDATE public.orders SET status='ready',batch_id=NULL,assigned_at=NULL WHERE id=ANY(v_all_ids);
            UPDATE public.order_status_logs SET changed_by=p_actor_id,note='Delivery batch cancelled',
                metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('batch_action','cancel','batch_id',p_batch_id)
              WHERE order_id=ANY(v_newly_assigned) AND status::text='ready'
                AND note='Auto-logged by trigger' AND changed_by IS NULL AND created_at>=transaction_timestamp();
            INSERT INTO public.order_status_logs(order_id,status,changed_by,note,metadata,campus_id)
              SELECT id,status,p_actor_id,'Delivery batch cancelled',jsonb_build_object('batch_action','cancel','batch_id',p_batch_id),campus_id
              FROM public.orders WHERE id=ANY(v_all_ids) AND NOT id=ANY(v_newly_assigned);
            UPDATE public.delivery_batches SET status='cancelled' WHERE id=p_batch_id RETURNING * INTO v_result;
            RETURN to_jsonb(v_result)||jsonb_build_object('batch_id',p_batch_id,'orders_unassigned',cardinality(v_all_ids),'notify_rider',false);
        END IF;
        IF p_action='split' THEN
            IF cardinality(v_ids)>=cardinality(v_all_ids) OR NOT v_ids<@v_all_ids THEN RAISE EXCEPTION 'batch_conflict'; END IF;
            IF EXISTS(SELECT 1 FROM public.orders WHERE id=ANY(v_ids) AND (status::text<>'assigned' OR payment_status::text NOT IN ('paid','partially_refunded'))) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
            v_window_id := coalesce(v_batch.window_id,v_batch.delivery_window_id);
        ELSE
            v_rider_id := coalesce((p_body->>'rider_id')::uuid,v_batch.rider_id);
            IF p_body ? 'rider_id' AND p_body->>'rider_id' IS NULL THEN RAISE EXCEPTION 'batch_invalid'; END IF;
            v_status := coalesce(p_body->>'status',v_batch.status);
            IF v_batch.status='open' AND v_rider_id IS NOT NULL AND NOT p_body ? 'status' THEN v_status:='assigned'; END IF;
            IF v_status NOT IN ('open','assigned','in_progress','completed') OR (v_status IS DISTINCT FROM v_batch.status AND NOT
                ((v_batch.status='open' AND v_status='assigned') OR (v_batch.status IN ('assigned','in_progress') AND v_status='completed'))) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
            IF v_status='assigned' AND v_rider_id IS NULL THEN RAISE EXCEPTION 'batch_rider_invalid'; END IF;
            IF v_status='completed' AND EXISTS(SELECT 1 FROM public.orders WHERE batch_id=p_batch_id AND status::text NOT IN ('delivered','cancelled','refunded','unclaimed')) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
            IF v_rider_id IS DISTINCT FROM v_batch.rider_id OR (v_batch.status='open' AND v_status='assigned') THEN
                IF v_batch.status NOT IN ('open','assigned') OR EXISTS(SELECT 1 FROM public.orders WHERE batch_id=p_batch_id AND
                    (status::text NOT IN ('ready','assigned') OR payment_status::text NOT IN ('paid','partially_refunded'))) THEN RAISE EXCEPTION 'batch_conflict'; END IF;
                v_ids:=v_all_ids;
            END IF;
        END IF;
    END IF;
    -- A rider run must not combine separate occurrences of a weekly window.
    -- Check locked membership for both manual creates and staged assignment.
    IF p_action IN ('create','split') OR (p_action='update' AND cardinality(v_ids)>0) THEN
        IF EXISTS(SELECT 1 FROM public.orders o WHERE o.id=ANY(v_ids)
             AND o.is_scheduled AND o.scheduled_for IS NULL)
           OR (SELECT count(DISTINCT (CASE WHEN o.is_scheduled THEN o.scheduled_for
                     ELSE o.created_at END AT TIME ZONE 'Africa/Lagos')::date)
               FROM public.orders o WHERE o.id=ANY(v_ids))>1 THEN
            RAISE EXCEPTION 'batch_conflict';
        END IF;
    END IF;
    IF p_action IN ('create','split') OR cardinality(v_ids)>0 OR (p_action='update' AND v_rider_id IS DISTINCT FROM v_batch.rider_id) THEN
        SELECT * INTO v_rider FROM public.profiles WHERE id=v_rider_id AND is_active AND role::text='rider' FOR SHARE;
        IF NOT FOUND OR v_rider.campus_id IS DISTINCT FROM v_campus_id THEN RAISE EXCEPTION 'batch_rider_invalid'; END IF;
    END IF;
    IF p_action IN ('create','split') THEN
        -- A manually chosen group may span gates. When it has one actual gate,
        -- persist that reference so the rider's existing nearest-neighbour route
        -- starts at the configured gate rather than falling back to creation order.
        SELECT count(DISTINCT g.id),count(*) FILTER (WHERE g.id IS NULL),
               (array_agg(g.id ORDER BY g.id))[1]
          INTO v_gate_count,v_missing_gates,v_gate_id
          FROM public.orders o
          LEFT JOIN public.hostels h ON o.delivery_type='on_campus' AND h.id=o.delivery_location_id
            AND (h.campus_id=v_campus_id OR h.campus_id IS NULL)
          LEFT JOIN public.gates g ON g.id=CASE WHEN o.delivery_type='off_campus' THEN o.delivery_location_id ELSE h.gate_id END
            AND (g.campus_id=v_campus_id OR g.campus_id IS NULL)
          WHERE o.id=ANY(v_ids);
        IF v_gate_count<>1 OR v_missing_gates>0 THEN v_gate_id:=NULL; END IF;
        IF v_zone='' AND v_gate_id IS NOT NULL THEN
            SELECT name INTO v_zone FROM public.gates WHERE id=v_gate_id;
        END IF;
        INSERT INTO public.delivery_batches(id,window_id,delivery_window_id,rider_id,zone,status,campus_id,notes,gate_id)
        VALUES(v_target_id,v_window_id,v_window_id,v_rider_id,v_zone,'assigned',v_campus_id,p_body->>'notes',v_gate_id) RETURNING * INTO v_result;
    ELSE
        UPDATE public.delivery_batches SET rider_id=v_rider_id,status=v_status,
            zone=CASE WHEN p_body ? 'zone' THEN trim(p_body->>'zone') ELSE zone END,
            notes=CASE WHEN p_body ? 'notes' THEN p_body->>'notes' ELSE notes END,
            completed_at=CASE WHEN v_status='completed' THEN coalesce(completed_at,now()) ELSE completed_at END
        WHERE id=p_batch_id RETURNING * INTO v_result;
        v_target_id:=p_batch_id;
    END IF;
    IF cardinality(v_ids)>0 THEN
        SELECT coalesce(array_agg(id ORDER BY id),ARRAY[]::uuid[]) INTO v_newly_assigned FROM public.orders WHERE id=ANY(v_ids) AND status::text='ready';
        INSERT INTO public.delivery_assignments(order_id,rider_id,batch_id,status,campus_id)
          SELECT id,v_rider_id,v_target_id,'assigned',v_campus_id FROM public.orders WHERE id=ANY(v_ids)
          ON CONFLICT(order_id) DO UPDATE SET rider_id=EXCLUDED.rider_id,batch_id=EXCLUDED.batch_id,status='assigned',completed_at=NULL,campus_id=EXCLUDED.campus_id;
        UPDATE public.orders SET batch_id=v_target_id,delivery_window_id=coalesce(delivery_window_id,v_window_id),status='assigned',assigned_at=coalesce(assigned_at,now()) WHERE id=ANY(v_ids);
        -- Trigger entries get the actor for actual state changes. Reassign/split
        -- produce an explicit operational log when status remains assigned.
        UPDATE public.order_status_logs SET changed_by=p_actor_id,note='Delivery batch assignment',metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('batch_action',p_action,'batch_id',v_target_id)
          WHERE order_id=ANY(v_newly_assigned) AND status::text='assigned' AND note='Auto-logged by trigger' AND changed_by IS NULL AND created_at>=transaction_timestamp();
        INSERT INTO public.order_status_logs(order_id,status,changed_by,note,metadata,campus_id)
          SELECT id,status,p_actor_id,'Delivery batch reassignment',jsonb_build_object('batch_action',p_action,'batch_id',v_target_id,'source_batch_id',p_batch_id),campus_id
          FROM public.orders WHERE id=ANY(v_ids) AND NOT id=ANY(v_newly_assigned);
    END IF;
    RETURN to_jsonb(v_result)||jsonb_build_object('orders_assigned',cardinality(v_ids),'orders_failed','[]'::jsonb,'newly_assigned',to_jsonb(v_newly_assigned),'notify_rider',cardinality(v_ids)>0);
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_manage_delivery_batch_atomic(uuid,text,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_manage_delivery_batch_atomic(uuid,text,uuid,jsonb) TO service_role;

