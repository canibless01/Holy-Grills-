-- Isolated role changes and synthetic orders; the whole transaction rolls back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 kitchen_id uuid; rider_id uuid; c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid();
 gate_id uuid:=gen_random_uuid(); window_id uuid:=gen_random_uuid(); oid uuid; bid uuid; result jsonb;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date; i integer;
BEGIN
 SELECT p.id INTO kitchen_id FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id
 WHERE p.is_active AND p.full_name ILIKE '%audit%' AND c.name ILIKE '%audit%' LIMIT 1;
 SELECT p.id INTO rider_id FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id
 WHERE p.is_active AND p.full_name ILIKE '%audit%' AND c.name ILIKE '%audit%' AND p.id<>kitchen_id LIMIT 1;
 IF kitchen_id IS NULL OR rider_id IS NULL THEN RAISE EXCEPTION 'two existing isolated actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Kitchen handoff','audit-handoff-'||c),
   (other_c,'[AUDIT rollback] Other campus','audit-handoff-'||other_c);
 UPDATE public.profiles SET role='kitchen',campus_id=c WHERE id=kitchen_id;
 UPDATE public.profiles SET role='rider',campus_id=c WHERE id=rider_id;
 INSERT INTO public.gates(id,name,campus_id) VALUES(gate_id,'[AUDIT rollback] Gate',c);
 INSERT INTO public.delivery_windows(id,label,opens_at,closes_at,campus_id) VALUES(window_id,'[AUDIT rollback] Evening','19:30','20:30',c);
 INSERT INTO public.orders(guest_email,campus_id,payment_status,is_scheduled,scheduled_for,delivery_type)
 VALUES('audit-handoff@example.invalid',c,'paid',true,((today+1)+'19:30'::time) AT TIME ZONE 'Africa/Lagos','off_campus') RETURNING id INTO oid;
 BEGIN
   UPDATE public.orders SET status='preparing' WHERE id=oid;
   RAISE EXCEPTION 'future order entered preparation';
 EXCEPTION WHEN check_violation THEN
   IF SQLERRM<>'order_preparation_day_not_due' THEN RAISE; END IF;
 END;
 FOR i IN 1..2 LOOP
   INSERT INTO public.orders(guest_email,campus_id,payment_status,is_scheduled,scheduled_for,delivery_type,delivery_location_id,delivery_window_id)
   VALUES('audit-handoff@example.invalid',c,'paid',true,(today+'23:59'::time) AT TIME ZONE 'Africa/Lagos','off_campus',gate_id,window_id) RETURNING id INTO oid;
   UPDATE public.orders SET status='preparing' WHERE id=oid;
   UPDATE public.orders SET status='ready' WHERE id=oid;
 END LOOP;
 SELECT batch_id INTO bid FROM public.orders WHERE id=oid;
 IF bid IS NULL OR (SELECT count(*) FROM public.orders WHERE batch_id=bid)<>2 THEN RAISE EXCEPTION 'today orders did not stage'; END IF;
 result:=public.hg_manage_delivery_batch_atomic(kitchen_id,'update',bid,jsonb_build_object('rider_id',rider_id));
 IF result->>'status'<>'assigned' OR (result->>'rider_id')::uuid<>rider_id
 OR (SELECT count(*) FROM public.orders WHERE batch_id=bid AND status='assigned')<>2
 THEN RAISE EXCEPTION 'kitchen assignment did not assign complete batch'; END IF;
 BEGIN
   PERFORM public.hg_manage_delivery_batch_atomic(kitchen_id,'cancel',bid,'{}');
   RAISE EXCEPTION 'kitchen gained batch cancellation permission';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN
   PERFORM public.hg_manage_delivery_batch_atomic(kitchen_id,'update',bid,jsonb_build_object('rider_id',rider_id,'status','completed'));
   RAISE EXCEPTION 'kitchen gained status/payout administration';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 UPDATE public.profiles SET campus_id=other_c WHERE id=kitchen_id;
 BEGIN
   PERFORM public.hg_manage_delivery_batch_atomic(kitchen_id,'update',bid,jsonb_build_object('rider_id',rider_id));
   RAISE EXCEPTION 'foreign campus kitchen assignment accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END;
$audit$;
SELECT 'passed' AS kitchen_handoff_and_due_day_checks;
ROLLBACK;
