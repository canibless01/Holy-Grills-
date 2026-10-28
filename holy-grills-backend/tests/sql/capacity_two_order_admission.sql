-- Real order admission/debits at capacity two, followed by deferred move-up.
-- No provider calls; isolated existing audit identity and fully rolled-back fixtures.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE u uuid; actor uuid; c uuid:=gen_random_uuid(); category uuid:=gen_random_uuid(); meal uuid:=gen_random_uuid();
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
 w1 uuid:=gen_random_uuid(); w2 uuid:=gen_random_uuid(); d1 uuid:=gen_random_uuid(); d2 uuid:=gen_random_uuid();
 result jsonb; line jsonb; deferred uuid; receipts jsonb; i integer; target_window uuid; target_delivery uuid;
 scheduled boolean:=false; target_time timestamptz; original_target date;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role::text='super_admin' AND is_active LIMIT 1;
 SELECT p.id INTO u FROM public.profiles p JOIN public.wallets w ON w.user_id=p.id
 WHERE p.role::text='student' AND p.full_name ILIKE '%audit%' AND p.is_active LIMIT 1;
 IF u IS NULL OR actor IS NULL THEN RAISE EXCEPTION 'isolated audit student and active actor required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Two-order capacity','audit-cap-two-'||c);
 UPDATE public.profiles SET campus_id=c,next_order_hp_multiplier=1,next_order_free_delivery_cap=0 WHERE id=u;
 UPDATE public.wallets SET balance=5000 WHERE user_id=u;
 INSERT INTO public.kitchen_settings(campus_id,key,value) VALUES(c,'daily_order_capacity','2');
 INSERT INTO public.delivery_windows(id,label,opens_at,closes_at,campus_id)
 VALUES(d1,'[AUDIT rollback] Today','19:00','20:00',c),(d2,'[AUDIT rollback] Tomorrow','19:00','20:00',c);
 INSERT INTO public.ordering_windows(id,campus_id,date,opens_at,closes_at,capacity,linked_delivery_window_id)
 VALUES(w1,c,today,'00:00','23:59:59',2,d1),(w2,c,today+1,'00:00','23:59:59',2,d2);
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Capacity','audit-cap-'||category,c);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id)
 VALUES(meal,category,'[AUDIT rollback] Meal','audit-cap-'||meal,100,10,c);
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,
 'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,
 'options_snapshot','{}'::jsonb,'selected_variations','[]'::jsonb);
 FOR i IN 1..4 LOOP
   scheduled:=i=4;target_window:=CASE WHEN scheduled THEN w2 ELSE w1 END;
   target_delivery:=CASE WHEN scheduled THEN d2 ELSE d1 END;
   target_time:=CASE WHEN scheduled THEN ((today+1)+'00:00'::time) AT TIME ZONE 'Africa/Lagos' ELSE NULL END;
   original_target:=CASE WHEN scheduled THEN today ELSE NULL END;
   result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
     p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
     p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>target_delivery,
     p_squad_name=>null,p_notes=>'[AUDIT rollback] Capacity admission',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,
     p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>target_window,
     p_is_scheduled=>scheduled,p_scheduled_for=>target_time,p_capacity_deferred=>scheduled,p_originally_requested_date=>original_target);
   IF i=3 THEN
     IF result->>'error' IS NULL OR (SELECT balance FROM public.wallets WHERE user_id=u)<>4800
       OR (SELECT count(*) FROM public.orders WHERE campus_id=c)<>2 THEN RAISE EXCEPTION 'third same-day admission exceeded capacity or debited wallet: %',result; END IF;
   ELSE
     IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'order admission % failed: %',i,result; END IF;
     IF i=4 THEN deferred:=(result->>'order_id')::uuid; END IF;
   END IF;
 END LOOP;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>4700
 OR (SELECT (scheduled_for AT TIME ZONE 'Africa/Lagos')::date FROM public.orders WHERE id=deferred)<>today+1 THEN RAISE EXCEPTION 'overflow was not paid once and scheduled tomorrow'; END IF;
 UPDATE public.ordering_windows SET capacity=3 WHERE id=w1;
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w1,today))<>0 THEN RAISE EXCEPTION 'window increase bypassed daily cap'; END IF;
 UPDATE public.kitchen_settings SET value='3' WHERE campus_id=c AND key='daily_order_capacity';
 receipts:=public.hg_move_deferred_orders_atomic(actor,w1,today);
 IF jsonb_array_length(receipts)<>1 OR (receipts->0->>'id')::uuid IS DISTINCT FROM deferred
 OR receipts->0->>'deliv_start'<>'19:00' OR receipts->0->>'deliv_end'<>'20:00'
 OR (SELECT (scheduled_for AT TIME ZONE 'Africa/Lagos')::date FROM public.orders WHERE id=deferred)<>today
 OR (SELECT delivery_window_id FROM public.orders WHERE id=deferred) IS DISTINCT FROM d1
 OR (SELECT capacity_deferred FROM public.orders WHERE id=deferred)
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>4700 THEN RAISE EXCEPTION 'capacity increase did not move paid overflow and delivery metadata together: %',receipts; END IF;
 IF jsonb_array_length(public.hg_move_deferred_orders_atomic(actor,w1,today))<>0 THEN RAISE EXCEPTION 'move-up replay changed another order'; END IF;
 -- Weekly closed rows can be reopened by a one-date override. A later close
 -- blocks admission; an explicit dated ordering window still takes priority.
 UPDATE public.kitchen_settings SET value='10' WHERE campus_id=c AND key='daily_order_capacity';
 UPDATE public.ordering_windows SET date=null,weekday=extract(isodow FROM today)::int-1,is_closed=true,capacity=10 WHERE id=w1;
 INSERT INTO public.operating_hour_overrides(date,campus_id,is_closed,opens_at,closes_at)
 VALUES(today,c,false,'00:00','23:59');
 target_window:=w1;target_delivery:=d1;scheduled:=false;target_time:=null;original_target:=null;
   result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
     p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
     p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>target_delivery,
     p_squad_name=>null,p_notes=>'[AUDIT rollback] Capacity admission',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,
     p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>target_window,
     p_is_scheduled=>scheduled,p_scheduled_for=>target_time,p_capacity_deferred=>scheduled,p_originally_requested_date=>original_target);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'open date override could not admit closed weekly window: %',result; END IF;
 UPDATE public.operating_hour_overrides SET is_closed=true WHERE campus_id=c AND date=today;
   result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
     p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
     p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>target_delivery,
     p_squad_name=>null,p_notes=>'[AUDIT rollback] Capacity admission',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,
     p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>target_window,
     p_is_scheduled=>scheduled,p_scheduled_for=>target_time,p_capacity_deferred=>scheduled,p_originally_requested_date=>original_target);
 IF result->>'error' IS DISTINCT FROM 'ORDERING_WINDOW_CLOSED' THEN RAISE EXCEPTION 'closed override admitted weekly order: %',result; END IF;
 target_window:=gen_random_uuid();
 INSERT INTO public.ordering_windows(id,campus_id,date,opens_at,closes_at,capacity,linked_delivery_window_id)
 VALUES(target_window,c,today,'00:00','23:59',10,d1);
   result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
     p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
     p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>target_delivery,
     p_squad_name=>null,p_notes=>'[AUDIT rollback] Capacity admission',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,
     p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>target_window,
     p_is_scheduled=>scheduled,p_scheduled_for=>target_time,p_capacity_deferred=>scheduled,p_originally_requested_date=>original_target);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'dated window did not take priority: %',result; END IF;
END $audit$;
ROLLBACK;
SELECT 'two actual admissions; third same-day refusal; overflow tomorrow; increased capacity moves it back with no second charge; rollback complete' AS evidence;
