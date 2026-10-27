-- Execute against Test Two with a privileged audit connection. All rows roll back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 c uuid:=gen_random_uuid(); g uuid:=gen_random_uuid(); w uuid:=gen_random_uuid();
 a uuid; r uuid; b1 uuid; b2 uuid; b3 uuid; x uuid; actor uuid;
 ids uuid[]:=ARRAY[]::uuid[];
 i integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Batch dates','audit-batch-dates-'||c);
 INSERT INTO public.gates(id,name,campus_id) VALUES(g,'[AUDIT rollback] Gate',c);
 INSERT INTO public.delivery_windows(id,label,opens_at,closes_at,campus_id,is_active)
 VALUES(w,'[AUDIT rollback] Closed repeating window','19:30','20:30',c,false);
 -- Same recurring window, two different delivery dates, both booked earlier.
 FOR i IN 1..3 LOOP
   INSERT INTO public.orders(guest_email,campus_id,status,payment_status,delivery_type,
      delivery_location_id,delivery_window_id,is_scheduled,scheduled_for,created_at)
   VALUES('audit-batch@example.invalid',c,'ready','paid','off_campus',g,w,true,
      CASE WHEN i=3 THEN '2026-11-03T19:30:00+01:00'::timestamptz
           ELSE '2026-10-27T19:30:00+01:00'::timestamptz END,
      '2026-10-26T10:00:00+01:00') RETURNING id INTO a;
   ids:=array_append(ids,a);
 END LOOP;
 SELECT batch_id INTO b1 FROM public.orders WHERE id=ids[1];
 SELECT batch_id INTO b2 FROM public.orders WHERE id=ids[3];
 IF b1 IS NULL OR b2 IS NULL OR b1=b2 OR
   (SELECT batch_id FROM public.orders WHERE id=ids[2]) IS DISTINCT FROM b1 THEN
   RAISE EXCEPTION 'scheduled delivery-date isolation failed';
 END IF;
 IF (SELECT delivery_date FROM public.delivery_batches WHERE id=b1) IS DISTINCT FROM date '2026-10-27'
 OR (SELECT delivery_date FROM public.delivery_batches WHERE id=b2) IS DISTINCT FROM date '2026-11-03'
 THEN RAISE EXCEPTION 'saved batch dates failed'; END IF;
 -- An immediate order outside an ordering window joins its actual delivery day.
 INSERT INTO public.orders(guest_email,campus_id,status,payment_status,delivery_type,
   delivery_location_id,delivery_window_id,created_at)
 VALUES('audit-batch@example.invalid',c,'ready','paid','off_campus',g,w,'2026-10-27T23:00:00+01:00') RETURNING id INTO a;
 IF (SELECT batch_id FROM public.orders WHERE id=a) IS DISTINCT FROM b1
 THEN RAISE EXCEPTION 'outside-ordering-window grouping failed'; END IF;
 -- UTC day differs from local business day: 23:30 UTC belongs to the next day.
 INSERT INTO public.orders(guest_email,campus_id,status,payment_status,delivery_type,
   delivery_location_id,delivery_window_id,created_at)
 VALUES('audit-batch@example.invalid',c,'ready','paid','off_campus',g,w,'2026-10-27T23:30:00Z') RETURNING id INTO a;
 SELECT batch_id INTO b3 FROM public.orders WHERE id=a;
 IF b3 IS NULL OR b3 IN(b1,b2) OR
 (SELECT delivery_date FROM public.delivery_batches WHERE id=b3) IS DISTINCT FROM date '2026-10-28'
 THEN RAISE EXCEPTION 'Lagos midnight boundary failed'; END IF;
 IF public.hg_auto_assign_order_to_batch(a) IS DISTINCT FROM b3
 THEN RAISE EXCEPTION 'staging replay changed batch'; END IF;
 -- Pending payment and unknown scheduled date must not authorize staging.
 INSERT INTO public.orders(guest_email,campus_id,status,payment_status,delivery_type,
   delivery_location_id,delivery_window_id,is_scheduled,scheduled_for)
 VALUES('audit-batch@example.invalid',c,'received','pending','off_campus',g,w,false,null) RETURNING id INTO a;
 IF public.hg_auto_assign_order_to_batch(a) IS NOT NULL
 THEN RAISE EXCEPTION 'unpaid order staged'; END IF;
 INSERT INTO public.orders(guest_email,campus_id,status,payment_status,delivery_type,
   delivery_location_id,delivery_window_id,is_scheduled,scheduled_for)
 VALUES('audit-batch@example.invalid',c,'ready','paid','off_campus',g,w,true,null) RETURNING id INTO a;
 IF (SELECT batch_id FROM public.orders WHERE id=a) IS NOT NULL
 THEN RAISE EXCEPTION 'unknown scheduled date staged'; END IF;
 -- Explicit manual assignment also rejects dates that cannot share one run.
 UPDATE public.orders SET batch_id=null WHERE id=ANY(ids);
 SELECT id INTO actor FROM public.profiles WHERE role::text='super_admin' AND is_active LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'audit requires existing active super-admin'; END IF;
 BEGIN
   PERFORM public.hg_manage_delivery_batch_atomic(actor,'create',null,
     jsonb_build_object('window_id',w,'rider_id',gen_random_uuid(),'order_ids',jsonb_build_array(ids[1],ids[3])));
   RAISE EXCEPTION 'mixed-date manual create was accepted';
 EXCEPTION WHEN OTHERS THEN
   IF SQLERRM<>'batch_conflict' THEN RAISE; END IF;
 END;
 IF EXISTS(SELECT 1 FROM public.delivery_assignments da JOIN public.orders o ON o.id=da.order_id WHERE o.campus_id=c)
 OR EXISTS(SELECT 1 FROM public.delivery_batches WHERE campus_id=c AND rider_id IS NOT NULL)
 THEN RAISE EXCEPTION 'staging granted rider access'; END IF;
END;
$audit$;
SELECT 'passed' AS batch_delivery_date_checks, 'all fixtures rolled back' AS fixture_policy;
ROLLBACK;
