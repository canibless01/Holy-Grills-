-- Verify the real FUTA calendar without committing orders or charging a provider.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:='70000001-cafe-cafe-cafe-000000000001'; category uuid:=gen_random_uuid(); meal uuid:=gen_random_uuid();
 line jsonb; result jsonb; chosen date; intake uuid; delivery uuid; oid uuid;
BEGIN
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Prelaunch','audit-prelaunch-'||category,c);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id) VALUES(meal,category,'[AUDIT rollback] Prelaunch meal','audit-prelaunch-'||meal,100,0,c);
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Prelaunch meal','quantity',1,'price_snapshot',100,'line_total',100,'hp_earn_snapshot',0,'hp_multiplier_snapshot',1,'is_addon',false,'options_snapshot','{}'::jsonb,'selected_variations','[]'::jsonb);
 FOREACH chosen IN ARRAY ARRAY[date '2026-11-05',date '2026-11-08',date '2026-11-09'] LOOP
  SELECT id INTO intake FROM public.ordering_windows WHERE campus_id=c AND (date=chosen OR (date IS NULL AND weekday=extract(isodow FROM chosen)::int-1)) ORDER BY date NULLS LAST LIMIT 1;
  SELECT id INTO delivery FROM public.delivery_windows WHERE campus_id=c AND (date=chosen OR (date IS NULL AND weekday=extract(isodow FROM chosen)::int-1)) ORDER BY date NULLS LAST LIMIT 1;
  result:=public.hg_create_order_atomic(p_user_id=>null,p_guest_name=>'[AUDIT rollback] Prelaunch guest',p_guest_email=>'audit-prelaunch@example.invalid'::citext,p_guest_phone=>'08000000000',p_claim_token=>gen_random_uuid(),p_subtotal=>100,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>100,p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>delivery,p_squad_name=>null,p_notes=>'[AUDIT rollback] Prelaunch admission',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_card_amount_used=>100,p_campus_id=>c,p_ordering_window_id=>intake,p_is_scheduled=>true,p_scheduled_for=>(chosen+'19:30'::time) AT TIME ZONE 'Africa/Lagos');
  IF chosen<date '2026-11-09' THEN
   IF coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'prelaunch closed date admitted: %',chosen; END IF;
  ELSE
   IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'Monday preorder refused: %',result; END IF;
   oid:=(result->>'order_id')::uuid;
   PERFORM public.hg_mark_order_paid(oid,'paystack','AUDIT-ROLLBACK-'||oid,100,'{}');
   BEGIN
    UPDATE public.orders SET status='preparing' WHERE id=oid;
    RAISE EXCEPTION 'Monday preorder entered preparation early';
   EXCEPTION WHEN check_violation THEN
    IF SQLERRM<>'order_preparation_day_not_due' THEN RAISE; END IF;
   END;
  END IF;
 END LOOP;
END $verify$;
ROLLBACK;
SELECT 'PASS: real FUTA dated prelaunch closure, Sunday refusal, Monday preorder acceptance/payment, and refusal to prepare Monday food early. All test rows rolled back.' as evidence;
