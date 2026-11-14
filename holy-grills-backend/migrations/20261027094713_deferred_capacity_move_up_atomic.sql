-- Reuse existing order/window fields and admission's campus/day lock.
CREATE OR REPLACE FUNCTION public.hg_move_deferred_orders_atomic(
 p_actor_id uuid,p_window_id uuid,p_target_date date
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE
 w public.ordering_windows%ROWTYPE; d public.delivery_windows%ROWTYPE;
 actor public.profiles%ROWTYPE; candidate public.orders%ROWTYPE;
 used integer; daily_used integer; daily_cap integer; weight integer;
 target_time timestamptz; moved jsonb:='[]'::jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'move_up_forbidden' USING ERRCODE='42501'; END IF;
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor_id AND is_active;
 SELECT * INTO w FROM public.ordering_windows WHERE id=p_window_id;
 IF w.id IS NULL OR actor.id IS NULL OR actor.role::text NOT IN ('admin','super_admin')
 OR (actor.role::text<>'super_admin' AND actor.campus_id IS DISTINCT FROM w.campus_id)
 THEN RAISE EXCEPTION 'move_up_forbidden' USING ERRCODE='42501'; END IF;
 IF p_target_date IS NULL OR p_target_date<(now() AT TIME ZONE 'Africa/Lagos')::date
 OR p_target_date>(now() AT TIME ZONE 'Africa/Lagos')::date+14 OR w.is_closed
 OR (w.date IS NOT NULL AND w.date<>p_target_date)
 OR (w.date IS NULL AND w.weekday IS DISTINCT FROM (extract(isodow FROM p_target_date)::integer-1))
 THEN RETURN moved; END IF;
 -- A dated closure/override takes precedence over a recurring window.
 IF w.date IS NULL AND EXISTS(SELECT 1 FROM public.ordering_windows ow
   WHERE ow.campus_id=w.campus_id AND ow.date=p_target_date) THEN RETURN moved; END IF;
 IF (p_target_date+w.closes_at) AT TIME ZONE 'Africa/Lagos'<=now() THEN RETURN moved; END IF;
 SELECT * INTO d FROM public.delivery_windows WHERE id=w.linked_delivery_window_id
   AND campus_id=w.campus_id AND is_active AND NOT coalesce(is_closed,false);
 IF d.id IS NULL OR d.opens_at IS NULL OR d.closes_at IS NULL
 OR (d.date IS NOT NULL AND d.date<>p_target_date)
 OR (d.date IS NULL AND d.weekday IS NOT NULL AND d.weekday<>(extract(isodow FROM p_target_date)::integer-1))
 OR (p_target_date+d.closes_at) AT TIME ZONE 'Africa/Lagos'<=now() THEN RETURN moved; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('hg-order:'||w.campus_id::text||':'||p_target_date::text,0));
 SELECT coalesce(sum(CASE WHEN is_squad_order THEN greatest(coalesce(squad_item_count,1),1) ELSE 1 END),0)
 INTO used FROM public.orders WHERE campus_id=w.campus_id AND ordering_window_id=w.id
 AND status NOT IN ('cancelled','refunded') AND
 (CASE WHEN is_scheduled THEN scheduled_for ELSE created_at END AT TIME ZONE 'Africa/Lagos')::date=p_target_date;
 SELECT CASE WHEN value ~ '^[0-9]+$' THEN value::integer ELSE NULL END INTO daily_cap
 FROM public.kitchen_settings WHERE key='daily_order_capacity' AND campus_id=w.campus_id LIMIT 1;
 SELECT coalesce(sum(CASE WHEN is_squad_order THEN greatest(coalesce(squad_item_count,1),1) ELSE 1 END),0)
 INTO daily_used FROM public.orders WHERE campus_id=w.campus_id
 AND status NOT IN ('cancelled','refunded') AND
 (CASE WHEN is_scheduled THEN scheduled_for ELSE created_at END AT TIME ZONE 'Africa/Lagos')::date=p_target_date;
 target_time:=greatest((p_target_date+w.opens_at) AT TIME ZONE 'Africa/Lagos',now());
 FOR candidate IN SELECT * FROM public.orders o WHERE o.campus_id=w.campus_id
   AND o.capacity_deferred AND o.is_scheduled AND o.status='received'
   AND o.payment_status::text IN ('paid','partially_refunded') AND o.batch_id IS NULL
   AND o.originally_requested_date<=p_target_date
   AND (o.scheduled_for AT TIME ZONE 'Africa/Lagos')::date>p_target_date
   AND NOT EXISTS(SELECT 1 FROM public.delivery_assignments da WHERE da.order_id=o.id)
   ORDER BY o.originally_requested_date,o.created_at,o.id FOR UPDATE OF o
 LOOP
   weight:=CASE WHEN candidate.is_squad_order THEN greatest(coalesce(candidate.squad_item_count,1),1) ELSE 1 END;
   IF (w.capacity IS NOT NULL AND used+weight>w.capacity)
     OR (daily_cap IS NOT NULL AND daily_used+weight>daily_cap) THEN CONTINUE; END IF;
   UPDATE public.orders SET ordering_window_id=w.id,delivery_window_id=d.id,
     scheduled_for=target_time,capacity_deferred=false WHERE id=candidate.id;
   used:=used+weight; daily_used:=daily_used+weight;
   moved:=moved||jsonb_build_array(jsonb_build_object('id',candidate.id,'user_id',candidate.user_id,
     'guest_email',candidate.guest_email,'guest_name',candidate.guest_name,
     'originally_requested_date',candidate.originally_requested_date,'target_date',p_target_date,
     'deliv_start',to_char(d.opens_at,'HH24:MI'),'deliv_end',to_char(d.closes_at,'HH24:MI')));
 END LOOP;
 RETURN moved;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_move_deferred_orders_atomic(uuid,uuid,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_move_deferred_orders_atomic(uuid,uuid,date) TO service_role;
