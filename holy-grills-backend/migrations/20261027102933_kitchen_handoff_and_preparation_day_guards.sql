-- Limited own-campus kitchen rider assignment and preparation-day enforcement.
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
    IF NOT FOUND OR v_actor.role::text NOT IN ('admin','super_admin','kitchen') THEN RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501'; END IF;
    IF v_actor.role::text='kitchen' AND (p_action IS DISTINCT FROM 'update'
       OR jsonb_typeof(p_body) IS DISTINCT FROM 'object' OR NOT p_body ? 'rider_id'
       OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_body) k WHERE k<>'rider_id')) THEN
        RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501';
    END IF;
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
        IF v_actor.role::text='kitchen' AND (v_batch.status NOT IN ('open','assigned')
          OR EXISTS(SELECT 1 FROM public.orders o WHERE o.batch_id=p_batch_id
            AND o.is_scheduled AND (o.scheduled_for IS NULL
              OR (o.scheduled_for AT TIME ZONE 'Africa/Lagos')::date>(now() AT TIME ZONE 'Africa/Lagos')::date))) THEN
            RAISE EXCEPTION 'batch_forbidden' USING ERRCODE='42501';
        END IF;
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
        INSERT INTO public.delivery_batches(id,window_id,delivery_window_id,rider_id,zone,status,campus_id,notes,gate_id,delivery_date)
        VALUES(v_target_id,v_window_id,v_window_id,v_rider_id,v_zone,'assigned',v_campus_id,p_body->>'notes',v_gate_id,
          (SELECT (CASE WHEN o.is_scheduled THEN o.scheduled_for ELSE o.created_at END
            AT TIME ZONE 'Africa/Lagos')::date FROM public.orders o WHERE o.id=ANY(v_ids) LIMIT 1)) RETURNING * INTO v_result;
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
CREATE OR REPLACE FUNCTION public.hg_verify_order_status_transition()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_allowed text[];
BEGIN
  IF (TG_OP='INSERT' OR NEW.status IS DISTINCT FROM OLD.status)
    AND NEW.status::text IN ('preparing','ready','assigned','out_for_delivery','delivered','delivery_attempted','unclaimed')
    AND NEW.is_scheduled AND (NEW.scheduled_for IS NULL
      OR (NEW.scheduled_for AT TIME ZONE 'Africa/Lagos')::date>(now() AT TIME ZONE 'Africa/Lagos')::date) THEN
    RAISE EXCEPTION 'order_preparation_day_not_due' USING ERRCODE='23514';
  END IF;
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
