-- Private synthetic campus/actors. No transport calls. Entire run rolls back.
BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); k uuid:=gen_random_uuid();
 w uuid:=gen_random_uuid(); category uuid:=gen_random_uuid(); meal uuid:=gen_random_uuid(); o uuid; future_o uuid; pending_o uuid; d uuid; result jsonb; replay jsonb; line jsonb;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date; intent text:=gen_random_uuid()::text;
 i integer; original_o uuid; a uuid:=gen_random_uuid();r uuid:=gen_random_uuid();store uuid:=gen_random_uuid();plan jsonb;data jsonb;v timestamptz;
 location jsonb:='{"name":"Rollback store","address":"12 Test road","instructions":"Order number required"}';
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Store pickup','audit-pickup-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-pickup-'||u||'@example.invalid','{}'),(k,'audit-pickup-'||k||'@example.invalid','{}');
 INSERT INTO public.profiles(id,email) VALUES(u,'audit-pickup-'||u||'@example.invalid'),(k,'audit-pickup-'||k||'@example.invalid') ON CONFLICT(id) DO NOTHING;
 UPDATE public.profiles SET campus_id=c,role='student',is_active=true,next_order_hp_multiplier=1,next_order_free_delivery_cap=100 WHERE id=u;
 UPDATE public.profiles SET campus_id=c,role='kitchen',is_active=true WHERE id=k;
 INSERT INTO public.wallets(user_id,balance) VALUES(u,1000) ON CONFLICT(user_id) DO UPDATE SET balance=1000;
 INSERT INTO public.system_settings(key,value,campus_id,is_public) VALUES('store_pickup_location',location,c,false);
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('store_pickup',false,c);
 BEGIN
   INSERT INTO public.orders(guest_email,campus_id,delivery_type,delivery_address_snapshot) VALUES('audit-pickup@example.invalid',c,'store_pickup',jsonb_build_object('line1','12 Test road','location_name','Rollback store'));
   RAISE EXCEPTION 'disabled pickup admitted';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'store_pickup_unavailable' THEN RAISE; END IF; END;
 UPDATE public.feature_flags SET is_active=true WHERE feature_name='store_pickup' AND campus_id=c;
 BEGIN
   INSERT INTO public.orders(guest_email,campus_id,delivery_type,delivery_address_snapshot) VALUES('audit-pickup@example.invalid',c,'store_pickup','{"line1":"Forged","location_name":"Rollback store"}');
   RAISE EXCEPTION 'forged pickup address admitted';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'store_pickup_location_changed' THEN RAISE; END IF; END;
 INSERT INTO public.kitchen_settings(campus_id,key,value) VALUES(c,'daily_order_capacity','10');
 INSERT INTO public.ordering_windows(id,campus_id,date,opens_at,closes_at,capacity) VALUES(w,c,today,'00:00','23:59:59',10);
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Pickup','audit-pickup-'||category,c);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id) VALUES(meal,category,'[AUDIT rollback] Pickup meal','audit-pickup-'||meal,100,10,c);
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Pickup meal','quantity',1,
   'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,'options_snapshot','{}','selected_variations','[]'::jsonb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'store-admin-'||a||'@example.invalid','{}'),(r,'store-rider-'||r||'@example.invalid','{}');
 UPDATE public.profiles SET role='admin',campus_id=c,is_active=true WHERE id=a;
 UPDATE public.profiles SET role='rider',campus_id=c,is_active=true WHERE id=r;
 data:=jsonb_build_object('name',location->>'name','slug',store::text,'address',location->>'address','instructions',location->>'instructions','lat',7.3,'lon',5.14,'is_active',true,'pickup_enabled',true,'delivery_enabled',true);
 result:=public.hg_save_store(a,store,c,data,NULL);v:=(result->>'updated_at')::timestamptz;
 PERFORM public.hg_set_store_staff(a,store,ARRAY[k,r],v);
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('multi_store_ordering',true,c);
 SELECT jsonb_build_object('id',id,'name',name,'address',address,'instructions',instructions,'lat',lat,'lon',lon) INTO plan FROM public.stores WHERE id=store;
 FOR i IN 1..2 LOOP
 result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'store_pickup',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>jsonb_build_object('line1','12 Test road','location_name','Rollback store','instructions','Order number required','_fulfilment_store',plan),p_delivery_window_id=>null,
   p_squad_name=>null,p_notes=>'[AUDIT rollback] Pickup',p_idempotency_key=>intent,p_promo_code_id=>null,
   p_items=>jsonb_build_array(line),p_wallet_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>w);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'pickup admission failed: %',result; END IF;
 o:=(result->>'order_id')::uuid;
 IF i=1 THEN original_o:=o; ELSE IF original_o IS DISTINCT FROM o THEN RAISE EXCEPTION 'pickup replay created duplicate'; END IF; END IF;
 END LOOP;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>900 OR (SELECT next_order_free_delivery_cap FROM public.profiles WHERE id=u)<>100
 OR (SELECT payment_status FROM public.orders WHERE id=o)<>'paid' THEN RAISE EXCEPTION 'pickup payment/credit conservation failed'; END IF;
 INSERT INTO public.orders(guest_email,campus_id,delivery_type,payment_status,is_scheduled,scheduled_for,delivery_address_snapshot)
 VALUES('audit-pickup@example.invalid',c,'store_pickup','paid',true,((today+1)+'10:00'::time) AT TIME ZONE 'Africa/Lagos',jsonb_build_object('line1','12 Test road','location_name','Rollback store','_fulfilment_store',plan)) RETURNING id INTO future_o;
 BEGIN
   UPDATE public.orders SET status='preparing' WHERE id=future_o;
   RAISE EXCEPTION 'future pickup prepared early';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'order_preparation_day_not_due' THEN RAISE; END IF; END;
 INSERT INTO public.orders(guest_email,campus_id,delivery_type,delivery_address_snapshot)
 VALUES('audit-pickup@example.invalid',c,'store_pickup',jsonb_build_object('line1','12 Test road','location_name','Rollback store','_fulfilment_store',plan)) RETURNING id INTO pending_o;
 UPDATE public.feature_flags SET is_active=false WHERE feature_name='store_pickup' AND campus_id=c;
 -- Admission is now closed; paid existing pickup still prepares and completes.
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',k)::text,true);
 BEGIN
   UPDATE public.orders SET status='preparing' WHERE id=pending_o;
   RAISE EXCEPTION 'unpaid pickup prepared';
 EXCEPTION WHEN insufficient_privilege THEN IF SQLERRM<>'payment_required_for_preparation' THEN RAISE; END IF; END;
 UPDATE public.orders SET status='preparing' WHERE id=o;
 UPDATE public.orders SET status='ready' WHERE id=o;
 IF (SELECT batch_id FROM public.orders WHERE id=o) IS NOT NULL THEN RAISE EXCEPTION 'pickup entered rider batch'; END IF;
 UPDATE public.orders SET status='delivered',delivered_at=now() WHERE id=o;
 UPDATE public.orders SET status='delivered' WHERE id=o;
 IF (SELECT count(*) FROM public.order_status_logs WHERE order_id=o AND status='delivered')<>1 THEN RAISE EXCEPTION 'collection logged twice'; END IF;
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 BEGIN
   UPDATE public.orders SET delivery_fee=500 WHERE id=o;
   RAISE EXCEPTION 'pickup delivery fee accepted';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'store_pickup_invalid_delivery' THEN RAISE; END IF; END;
 BEGIN
   UPDATE public.orders SET delivery_type='off_campus' WHERE id=o;
   RAISE EXCEPTION 'pickup switched mode';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'store_pickup_mode_immutable' THEN RAISE; END IF; END;
 BEGIN
   INSERT INTO public.delivery_assignments(order_id,rider_id) VALUES(o,k);
   RAISE EXCEPTION 'pickup rider assignment accepted';
 EXCEPTION WHEN check_violation THEN IF SQLERRM<>'store_pickup_no_rider' THEN RAISE; END IF; END;
 -- Delivery keeps its old path; ready -> delivered remains invalid.
 INSERT INTO public.orders(guest_email,campus_id,delivery_type,payment_status,delivery_address_snapshot) VALUES('audit-pickup@example.invalid',c,'off_campus','paid',jsonb_build_object('_fulfilment_store',plan)) RETURNING id INTO d;
 UPDATE public.orders SET status='preparing' WHERE id=d;
 UPDATE public.orders SET status='ready' WHERE id=d;
 BEGIN
   UPDATE public.orders SET status='delivered' WHERE id=d;
   RAISE EXCEPTION 'delivery skipped rider stages';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM NOT LIKE 'Invalid order status transition:%' THEN RAISE; END IF; END;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>900 THEN RAISE EXCEPTION 'collection charged again'; END IF;
END $audit$;
SELECT 'MULTI-STORE pickup admission, payment, preparation, collection replay, future/unpaid guards, disabled release fulfillment, no rider/fee/mode switching, unchanged delivery path' AS verified;
ROLLBACK;
