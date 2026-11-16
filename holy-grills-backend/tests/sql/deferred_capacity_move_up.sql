-- Synthetic fixtures exist only inside this rolled-back transaction.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 c uuid:=gen_random_uuid(); w uuid:=gen_random_uuid(); d uuid:=gen_random_uuid();
 old_d uuid:=gen_random_uuid(); actor uuid; a uuid; first_id uuid; second_id uuid;
 target date:=(now() AT TIME ZONE 'Africa/Lagos')::date+1; receipts jsonb; i integer;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role::text='super_admin' AND is_active LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'active super-admin required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Capacity','audit-capacity-'||c);
 INSERT INTO public.delivery_windows(id,label,opens_at,closes_at,campus_id)
 VALUES(d,'[AUDIT rollback] Target','19:30','20:30',c),(old_d,'[AUDIT rollback] Later','21:00','22:00',c);
 INSERT INTO public.ordering_windows(id,campus_id,date,opens_at,closes_at,capacity,linked_delivery_window_id)
 VALUES(w,c,target,'08:00','18:00',2,d);
 -- One order occupies the target day. A later occurrence sharing its UUID must not consume its capacity.
 FOR i IN 0..1 LOOP
   INSERT INTO public.orders(guest_email,campus_id,payment_status,is_scheduled,scheduled_for,ordering_window_id,delivery_window_id)
   VALUES('audit-capacity@example.invalid',c,'paid',true,((target+i*7)+'08:00'::time) AT TIME ZONE 'Africa/Lagos',w,d);
 END LOOP;
 FOR i IN 1..4 LOOP
   INSERT INTO public.orders(guest_email,campus_id,payment_status,is_scheduled,scheduled_for,
     delivery_window_id,capacity_deferred,originally_requested_date,created_at)
   VALUES('audit-capacity@example.invalid',c,CASE WHEN i=3 THEN 'pending'::payment_status ELSE 'paid'::payment_status END,
     true,((target+3)+'08:00'::time) AT TIME ZONE 'Africa/Lagos',old_d,i<>4,target-1,
     now()-interval '1 hour'+i*interval '1 minute') RETURNING id INTO a;
   IF i=1 THEN first_id:=a; ELSIF i=2 THEN second_id:=a; END IF;
 END LOOP;
 receipts:=public.hg_move_deferred_orders_atomic(actor,w,target);
 IF jsonb_array_length(receipts)<>1 OR (receipts->0->>'id')::uuid<>first_id
 THEN RAISE EXCEPTION 'date-scoped capacity or oldest-first rule failed'; END IF;
 IF (SELECT delivery_window_id FROM public.orders WHERE id=first_id)<>d
 OR (SELECT ordering_window_id FROM public.orders WHERE id=first_id)<>w
 OR (SELECT (scheduled_for AT TIME ZONE 'Africa/Lagos')::date FROM public.orders WHERE id=first_id)<>target
 THEN RAISE EXCEPTION 'schedule and delivery mapping not moved together'; END IF;
 IF receipts->0->>'deliv_start'<>'19:30' OR receipts->0->>'deliv_end'<>'20:30'
 THEN RAISE EXCEPTION 'notification delivery hours missing'; END IF;
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w,target))<>0
 THEN RAISE EXCEPTION 'full-day replay moved another order'; END IF;
 UPDATE public.ordering_windows SET capacity=3 WHERE id=w;
 -- A daily kitchen cap is an independent ceiling.
 INSERT INTO public.kitchen_settings(campus_id,key,value) VALUES(c,'daily_order_capacity','2');
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w,target))<>0
 THEN RAISE EXCEPTION 'daily kitchen ceiling exceeded'; END IF;
 UPDATE public.kitchen_settings SET value='3' WHERE campus_id=c AND key='daily_order_capacity';
 receipts:=public.hg_move_deferred_orders_atomic(actor,w,target);
 IF jsonb_array_length(receipts)<>1 OR (receipts->0->>'id')::uuid<>second_id
 THEN RAISE EXCEPTION 'increased capacity did not move next waiting order'; END IF;
 UPDATE public.ordering_windows SET capacity=20 WHERE id=w;
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w,target))<>0
 THEN RAISE EXCEPTION 'unpaid or deliberately future order was moved'; END IF;
 -- Recurring windows also work; dated closures override them.
 UPDATE public.ordering_windows SET date=null,weekday=extract(isodow FROM target)::integer-1 WHERE id=w;
 INSERT INTO public.orders(guest_email,campus_id,payment_status,is_scheduled,scheduled_for,
   delivery_window_id,capacity_deferred,originally_requested_date)
 VALUES('audit-capacity@example.invalid',c,'paid',true,((target+4)+'08:00'::time) AT TIME ZONE 'Africa/Lagos',old_d,true,target-1);
 UPDATE public.kitchen_settings SET value='20' WHERE campus_id=c AND key='daily_order_capacity';
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w,target))<>1
 THEN RAISE EXCEPTION 'recurring capacity increase failed'; END IF;
 INSERT INTO public.ordering_windows(campus_id,date,opens_at,closes_at,is_closed)
 VALUES(c,target,'08:00','18:00',true);
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w,target))<>0
 THEN RAISE EXCEPTION 'dated closure did not override recurring window'; END IF;
END;
$audit$;
SELECT 'passed' AS deferred_capacity_checks;
ROLLBACK;
