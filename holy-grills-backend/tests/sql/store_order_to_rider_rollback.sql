-- Actual production constraints/RPCs/RLS, with fresh synthetic actors only.
-- No provider requests. Nothing in this transaction is committed.
BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE
 c uuid:=gen_random_uuid(); kitchen_id uuid:=gen_random_uuid(); rider_id uuid:=gen_random_uuid();
 other_rider uuid:=gen_random_uuid(); student_id uuid:=gen_random_uuid();
 gate_id uuid:=gen_random_uuid(); hostel_id uuid:=gen_random_uuid(); delivery_id uuid:=gen_random_uuid();
 intake_id uuid:=gen_random_uuid(); category_id uuid:=gen_random_uuid(); meal_id uuid:=gen_random_uuid();
 admin_id uuid:=gen_random_uuid(); kitchen_b uuid:=gen_random_uuid();store_a uuid:=gen_random_uuid();store_b uuid:=gen_random_uuid();third_order uuid;batch_b uuid;store_plan_a jsonb;store_plan_b jsonb;data jsonb;v timestamptz;
 first_order uuid; second_order uuid; batch uuid; result jsonb; line jsonb; changed integer;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date; intent text:=gen_random_uuid()::text;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Launch flow','audit-launch-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES
 (kitchen_id,'audit-kitchen-'||kitchen_id||'@example.invalid','{"full_name":"[AUDIT rollback] Kitchen"}'),
 (rider_id,'audit-rider-'||rider_id||'@example.invalid','{"full_name":"[AUDIT rollback] Rider"}'),
 (other_rider,'audit-other-'||other_rider||'@example.invalid','{"full_name":"[AUDIT rollback] Other rider"}'),
 (student_id,'audit-student-'||student_id||'@example.invalid','{"full_name":"[AUDIT rollback] Student"}');
 UPDATE public.profiles SET campus_id=c,role='kitchen' WHERE id=kitchen_id;
 UPDATE public.profiles SET campus_id=c,role='rider' WHERE id in(rider_id,other_rider);
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id=student_id;
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(admin_id,'store-admin-'||admin_id||'@example.invalid','{}'),(kitchen_b,'store-kitchen-'||kitchen_b||'@example.invalid','{}');
 UPDATE public.profiles SET role='admin',campus_id=c,is_active=true WHERE id=admin_id;
 UPDATE public.profiles SET role='kitchen',campus_id=c,is_active=true WHERE id=kitchen_b;
 data:=jsonb_build_object('name','[ROLLBACK] A','slug',store_a::text,'address','West gate counter','instructions','Collect here','lat',7.3,'lon',5.2,'is_active',true,'pickup_enabled',true,'delivery_enabled',true);
 result:=public.hg_save_store(admin_id,store_a,c,data,NULL);v:=(result->>'updated_at')::timestamptz;
 PERFORM public.hg_set_store_staff(admin_id,store_a,ARRAY[kitchen_id,rider_id],v);
 data:=data||jsonb_build_object('name','[ROLLBACK] B','slug',store_b::text,'address','North gate counter','lat',7.31);
 result:=public.hg_save_store(admin_id,store_b,c,data,NULL);v:=(result->>'updated_at')::timestamptz;
 PERFORM public.hg_set_store_staff(admin_id,store_b,ARRAY[kitchen_b,other_rider],v);
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('multi_store_ordering',true,c);
 SELECT jsonb_build_object('id',id,'name',name,'address',address,'instructions',instructions,'lat',lat,'lon',lon) INTO store_plan_a FROM public.stores WHERE id=store_a;
 SELECT jsonb_build_object('id',id,'name',name,'address',address,'instructions',instructions,'lat',lat,'lon',lon) INTO store_plan_b FROM public.stores WHERE id=store_b;
 UPDATE public.wallets SET balance=500 WHERE user_id=student_id;
 INSERT INTO public.gates(id,name,campus_id) VALUES(gate_id,'[AUDIT rollback] Gate',c);
 INSERT INTO public.hostels(id,name,campus_id,gate_id,delivery_fee) VALUES(hostel_id,'[AUDIT rollback] Hostel',c,gate_id,0);
 INSERT INTO public.delivery_windows(id,campus_id,date,label,opens_at,closes_at) VALUES(delivery_id,c,today,'[AUDIT rollback] Evening','19:30','20:30');
 INSERT INTO public.ordering_windows(id,campus_id,date,opens_at,closes_at,linked_delivery_window_id,capacity) VALUES(intake_id,c,today,'00:00','23:59:59',delivery_id,3);
 INSERT INTO public.kitchen_settings(campus_id,key,value) VALUES(c,'daily_order_capacity','3');
 INSERT INTO public.menu_categories(id,campus_id,name,slug) VALUES(category_id,c,'[AUDIT rollback] Category','audit-category-'||category_id);
 INSERT INTO public.menu_items(id,campus_id,category_id,name,slug,price,hp_earn_value) VALUES(meal_id,c,category_id,'[AUDIT rollback] Meal','audit-meal-'||meal_id,100,10);
 line:=jsonb_build_object('menu_item_id',meal_id,'name_snapshot','[AUDIT rollback] Meal','quantity',1,'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,'options_snapshot','{}'::jsonb,'selected_variations','[]'::jsonb);
 result:=public.hg_create_order_atomic(p_user_id=>null,p_guest_name=>'[AUDIT rollback] Guest',p_guest_email=>('audit-guest-'||c||'@example.invalid')::citext,p_guest_phone=>'08000000000',p_claim_token=>gen_random_uuid(),p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>gate_id,p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>jsonb_build_object('_fulfilment_store',store_plan_a),p_delivery_window_id=>delivery_id,p_squad_name=>null,p_notes=>'[AUDIT rollback] Guest card',p_idempotency_key=>intent,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_card_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>intake_id);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'guest creation failed: %',result; END IF;
 first_order:=(result->>'order_id')::uuid;
 IF (SELECT payment_status::text FROM public.orders WHERE id=first_order)<>'pending' THEN RAISE EXCEPTION 'unpaid guest incorrectly confirmed'; END IF;
 BEGIN
  UPDATE public.orders SET status='preparing' WHERE id=first_order;
  RAISE EXCEPTION 'unpaid guest entered kitchen';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 PERFORM public.hg_mark_order_paid(first_order,'paystack','AUDIT-ROLLBACK-'||first_order,100,'{}');
 PERFORM public.hg_mark_order_paid(first_order,'paystack','AUDIT-ROLLBACK-'||first_order,100,'{}');
 IF (SELECT payment_status::text FROM public.orders WHERE id=first_order)<>'paid' THEN RAISE EXCEPTION 'card receipt did not confirm payment'; END IF;
 result:=public.hg_create_order_atomic(p_user_id=>student_id,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'on_campus',p_delivery_location_id=>hostel_id,p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>jsonb_build_object('_fulfilment_store',store_plan_a),p_delivery_window_id=>delivery_id,p_squad_name=>null,p_notes=>'[AUDIT rollback] Wallet hostel',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>intake_id);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'wallet creation failed: %',result; END IF;
 second_order:=(result->>'order_id')::uuid;
 IF (SELECT balance FROM public.wallets WHERE user_id=student_id)<>400 THEN RAISE EXCEPTION 'wallet debit incorrect'; END IF;
 result:=public.hg_create_order_atomic(p_user_id=>student_id,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'on_campus',p_delivery_location_id=>hostel_id,p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>jsonb_build_object('_fulfilment_store',store_plan_b),p_delivery_window_id=>delivery_id,p_squad_name=>null,p_notes=>'[AUDIT rollback] Wallet hostel',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>intake_id);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'second store order failed: %',result;END IF;
 third_order:=(result->>'order_id')::uuid;
 IF (SELECT store_id FROM public.orders WHERE id=third_order)<>store_b THEN RAISE EXCEPTION 'store ownership missing';END IF;
 result:=public.hg_create_order_atomic(p_user_id=>student_id,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'on_campus',p_delivery_location_id=>hostel_id,p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>jsonb_build_object('_fulfilment_store',store_plan_b),p_delivery_window_id=>delivery_id,p_squad_name=>null,p_notes=>'[AUDIT rollback] Wallet hostel',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>intake_id);
 IF result->>'error' IS NULL OR (SELECT balance FROM public.wallets WHERE user_id=student_id)<>300 THEN RAISE EXCEPTION 'campus capacity was bypassed across stores';END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',kitchen_id)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.orders WHERE id=third_order) OR EXISTS(SELECT 1 FROM public.order_items WHERE order_id=third_order) THEN RAISE EXCEPTION 'cross-store kitchen read leaked';END IF;
 UPDATE public.orders SET status='preparing' WHERE id=third_order;GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>0 THEN RAISE EXCEPTION 'cross-store kitchen write succeeded';END IF;
 UPDATE public.orders SET status='preparing' WHERE id in(first_order,second_order); GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>2 THEN RAISE EXCEPTION 'kitchen could not prepare both paid orders'; END IF;
 UPDATE public.orders SET status='ready' WHERE id in(first_order,second_order); GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>2 THEN RAISE EXCEPTION 'kitchen could not ready both paid orders'; END IF;
 PERFORM set_config('role','none',true); PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 SELECT batch_id INTO batch FROM public.orders WHERE id=first_order;
 IF batch IS NULL OR (SELECT batch_id FROM public.orders WHERE id=second_order) IS DISTINCT FROM batch THEN RAISE EXCEPTION 'hostel and gate did not auto-group'; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',kitchen_b)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.orders SET status='preparing' WHERE id=third_order;UPDATE public.orders SET status='ready' WHERE id=third_order;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 SELECT batch_id INTO batch_b FROM public.orders WHERE id=third_order;
 IF batch_b IS NULL OR batch_b=batch OR (SELECT store_id FROM public.delivery_batches WHERE id=batch_b)<>store_b THEN RAISE EXCEPTION 'same campus/gate/window mixed stores';END IF;
 BEGIN PERFORM public.hg_manage_delivery_batch_atomic(kitchen_id,'update',batch_b,jsonb_build_object('rider_id',rider_id));RAISE EXCEPTION 'kitchen assigned another store';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM public.hg_manage_delivery_batch_atomic(admin_id,'update',batch_b,jsonb_build_object('rider_id',rider_id));RAISE EXCEPTION 'rider assigned outside store membership';EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT IN('batch_rider_invalid','HG_STORE_RIDER_UNAVAILABLE') THEN RAISE;END IF;END;
 result:=public.hg_manage_delivery_batch_atomic(kitchen_id,'update',batch,jsonb_build_object('rider_id',rider_id));
 IF result->>'status'<>'assigned' THEN RAISE EXCEPTION 'kitchen rider handoff failed: %',result; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',other_rider)::text,true); PERFORM set_config('role','authenticated',true);
 UPDATE public.orders SET status='out_for_delivery' WHERE id=first_order; GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>0 THEN RAISE EXCEPTION 'wrong rider could pick up order'; END IF;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',rider_id)::text,true); PERFORM set_config('role','authenticated',true);
 IF (SELECT count(*) FROM public.orders WHERE batch_id=batch)<>2 THEN RAISE EXCEPTION 'rider cannot see both batch orders'; END IF;
 UPDATE public.orders SET status='out_for_delivery' WHERE id in(first_order,second_order); GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>2 THEN RAISE EXCEPTION 'assigned rider could not confirm pickup'; END IF;
 UPDATE public.orders SET status='delivered' WHERE id in(first_order,second_order); GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>2 THEN RAISE EXCEPTION 'assigned rider could not deliver'; END IF;
 PERFORM set_config('role','none',true); PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF (SELECT status FROM public.delivery_batches WHERE id=batch)<>'completed' THEN RAISE EXCEPTION 'batch did not complete'; END IF;
 IF (public.hg_store_analytics(admin_id,c,store_a,now()-interval '1 day',now()+interval '1 day')->'rows'->0->>'retained_revenue')::numeric<>200 THEN RAISE EXCEPTION 'store revenue does not match its paid orders';END IF;
 IF jsonb_array_length(public.hg_store_analytics(admin_id,c,NULL,now()-interval '1 day',now()+interval '1 day')->'rows')<>2 THEN RAISE EXCEPTION 'campus comparison failed';END IF;
 IF (SELECT fulfilment_store_snapshot->>'address' FROM public.orders WHERE id=first_order)<>'West gate counter' THEN RAISE EXCEPTION 'order lost its frozen store address';END IF;
 -- Readable own payout/history must survive removal from an active store team.
 DELETE FROM hg_internal.store_staff WHERE store_id=store_a AND user_id=rider_id;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',rider_id)::text,true);PERFORM set_config('role','authenticated',true);
 IF (SELECT count(*) FROM public.orders WHERE id IN(first_order,second_order))<>2 OR (SELECT count(*) FROM public.delivery_batches WHERE id=batch)<>1 THEN RAISE EXCEPTION 'team change hid own delivered work or payout batch';END IF;
 UPDATE public.orders SET status='delivered' WHERE id=first_order;GET DIAGNOSTICS changed=ROW_COUNT;
 IF changed<>0 THEN RAISE EXCEPTION 'removed store rider retained write access';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 -- A completed partial refund reduces its original store, not another store.
 result:=public.hg_refund_order_atomic(second_order,admin_id,'store-refund-'||second_order,25,'[ROLLBACK] Approved partial refund',false);
 result:=public.hg_refund_order_atomic(second_order,admin_id,'store-refund-'||second_order,25,'[ROLLBACK] Approved partial refund',false);
 IF (SELECT wallet_refund_total FROM public.orders WHERE id=second_order)<>25 OR (SELECT balance FROM public.wallets WHERE user_id=student_id)<>325 THEN RAISE EXCEPTION 'store refund replay or wallet conservation failed: %',result;END IF;
 IF (public.hg_store_analytics(admin_id,c,store_a,now()-interval '1 day',now()+interval '1 day')->'rows'->0->>'retained_revenue')::numeric<>175
 OR (public.hg_store_analytics(admin_id,c,store_b,now()-interval '1 day',now()+interval '1 day')->'rows'->0->>'retained_revenue')::numeric<>100 THEN RAISE EXCEPTION 'refund attributed to wrong store';END IF;
 UPDATE public.stores SET address='Moved counter' WHERE id=store_a;
 IF (SELECT fulfilment_store_snapshot->>'address' FROM public.orders WHERE id=first_order)<>'West gate counter' THEN RAISE EXCEPTION 'store edit rewrote historic order';END IF;
 BEGIN UPDATE public.orders SET store_id=store_b WHERE id=first_order;RAISE EXCEPTION 'paid store ownership changed';EXCEPTION WHEN check_violation THEN IF SQLERRM<>'HG_STORE_ORDER_IMMUTABLE' THEN RAISE;END IF;END;
END $verify$;
ROLLBACK;
SELECT 'PASS: MULTI-STORE real scope, campus-wide capacity, isolated kitchen/batches/riders and recorded sales;  guest card pending/paid replay, wallet debit, unpaid prep refusal, real kitchen RLS, hostel/gate auto-group, kitchen rider assignment, wrong-rider refusal, pickup, delivery and batch completion. All synthetic records rolled back.' as evidence;
