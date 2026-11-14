-- Real redemption/order/stock/claim, authenticated kitchen/rider and refund loop.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[]; customer uuid; kitchen uuid; rider uuid; outsider uuid; admin uuid;
 c uuid:=gen_random_uuid(); g uuid:=gen_random_uuid(); w uuid:=gen_random_uuid(); reward uuid:=gen_random_uuid();
 redemption uuid; oid uuid; batch uuid; result jsonb; line jsonb; assigned jsonb; i integer; changed integer;
BEGIN
 SELECT array_agg(id) INTO ids FROM (SELECT p.id FROM public.profiles p JOIN public.wallets wa ON wa.user_id=p.id
 WHERE p.full_name ILIKE '%audit%' AND p.is_active ORDER BY p.id LIMIT 4) q;
 customer:=ids[1];kitchen:=ids[2];rider:=ids[3];outsider:=ids[4];
 SELECT id INTO admin FROM public.profiles WHERE role::text='super_admin' AND is_active AND id<>ALL(ids) LIMIT 1;
 IF outsider IS NULL OR admin IS NULL THEN RAISE EXCEPTION 'isolated audit actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Physical reward','audit-physical-'||c);
 UPDATE public.profiles SET campus_id=c,role=(CASE WHEN id=customer THEN 'student' WHEN id=kitchen THEN 'kitchen' ELSE 'rider' END)::public.user_role WHERE id=ANY(ids);
 UPDATE public.profiles SET hp_balance=10000,next_order_hp_multiplier=1,next_order_free_delivery_cap=0 WHERE id=customer;
 UPDATE public.wallets SET balance=5000 WHERE user_id=customer;
 INSERT INTO public.gates(id,name,campus_id,lat,lon) VALUES(g,'[AUDIT rollback] Gate',c,7.3,5.2);
 INSERT INTO public.delivery_windows(id,label,opens_at,closes_at,campus_id) VALUES(w,'[AUDIT rollback] Delivery','18:00','20:00',c);
 INSERT INTO public.rewards(id,name,hp_cost,reward_type,stock_quantity,max_per_user,campus_id)
 VALUES(reward,'[AUDIT rollback] Physical meal',100,'food',5,5,c);
 FOR i IN 1..3 LOOP
   result:=public.hg_redeem_reward(customer,reward);
   IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'redemption failed: %',result; END IF;
   redemption:=(result->>'redemption_id')::uuid;
   line:=jsonb_build_object('menu_item_id',null,'name_snapshot','[AUDIT rollback] Physical meal','quantity',1,
     'price_snapshot',0,'line_total',0,'hp_earn_snapshot',0,'hp_multiplier_snapshot',1,'is_addon',false,
     'selected_variations','[]'::jsonb,'_reward_claims',jsonb_build_array(redemption),
     'options_snapshot',jsonb_build_object('reward_redemption_id',redemption,'reward_name','[AUDIT rollback] Physical meal','reward_type','food'));
   result:=public.hg_create_order_atomic(p_user_id=>customer,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
     p_subtotal=>0,p_delivery_fee=>50,p_discount_amount=>0,p_total_amount=>50,p_delivery_type=>'off_campus',p_delivery_location_id=>g,
     p_delivery_location_lat=>7.3,p_delivery_location_lon=>5.2,p_delivery_address_snapshot=>'{"line1":"[AUDIT rollback] Junction","contact_phone":"+2348012345678"}',
     p_delivery_window_id=>w,p_squad_name=>null,p_notes=>'[AUDIT rollback] Reward delivery',p_idempotency_key=>gen_random_uuid()::text,
     p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>50,p_campus_id=>c,p_redemption_id=>redemption);
   IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'reward checkout failed: %',result; END IF;
   oid:=(result->>'order_id')::uuid;
   IF (SELECT attached_order_id FROM public.reward_redemptions WHERE id=redemption) IS DISTINCT FROM oid THEN RAISE EXCEPTION 'reward not attached'; END IF;
   IF i=3 THEN
     result:=public.hg_refund_order_atomic(oid,customer,'audit-early-cancel',null,'[AUDIT rollback]',true);
     IF NOT coalesce((result->>'success')::boolean,false) OR EXISTS(SELECT 1 FROM public.reward_redemptions WHERE id=redemption AND (attached_order_id IS NOT NULL OR used_at IS NOT NULL)) THEN RAISE EXCEPTION 'early cancel did not release unused reward'; END IF;
     CONTINUE;
   END IF;
   -- Actual authenticated kitchen role prepares and stages the paid order.
   PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',kitchen)::text,true);
   PERFORM set_config('role','authenticated',true);
   UPDATE public.orders SET status='preparing' WHERE id=oid; GET DIAGNOSTICS changed=ROW_COUNT;
   IF changed<>1 THEN RAISE EXCEPTION 'kitchen could not prepare owned-campus order'; END IF;
   UPDATE public.orders SET status='ready' WHERE id=oid;
   PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
   SELECT batch_id INTO batch FROM public.orders WHERE id=oid;
   IF batch IS NULL THEN RAISE EXCEPTION 'ready physical reward did not auto-stage'; END IF;
   assigned:=public.hg_manage_delivery_batch_atomic(kitchen,'update',batch,jsonb_build_object('rider_id',rider));
   IF (SELECT status::text FROM public.orders WHERE id=oid)<>'assigned' THEN RAISE EXCEPTION 'kitchen handoff did not assign order'; END IF;
   -- Another rider cannot see the order or its reward lines.
   PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',outsider)::text,true);
   PERFORM set_config('role','authenticated',true);
   IF EXISTS(SELECT 1 FROM public.orders WHERE id=oid) OR EXISTS(SELECT 1 FROM public.order_items WHERE order_id=oid) THEN RAISE EXCEPTION 'other rider could read reward order'; END IF;
   PERFORM set_config('role','none',true);
   PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',rider)::text,true);
   PERFORM set_config('role','authenticated',true);
   IF NOT EXISTS(SELECT 1 FROM public.order_items WHERE order_id=oid AND name_snapshot='[AUDIT rollback] Physical meal') THEN RAISE EXCEPTION 'assigned rider cannot see physical reward line'; END IF;
   UPDATE public.orders SET status='out_for_delivery' WHERE id=oid; GET DIAGNOSTICS changed=ROW_COUNT;
   IF changed<>1 THEN RAISE EXCEPTION 'rider pickup failed'; END IF;
   UPDATE public.orders SET status=CASE WHEN i=1 THEN 'delivered'::public.order_status ELSE 'delivery_attempted'::public.order_status END WHERE id=oid;
   PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
   IF i=2 THEN
     IF (SELECT status FROM public.delivery_batches WHERE id=batch)<>'in_progress' THEN RAISE EXCEPTION 'attempted delivery incorrectly closed batch'; END IF;
     UPDATE public.orders SET status='unclaimed' WHERE id=oid;
   END IF;
   IF (SELECT status FROM public.delivery_batches WHERE id=batch)<>'completed' THEN RAISE EXCEPTION 'terminal delivery did not close batch'; END IF;
   IF i=1 THEN
     result:=public.hg_refund_order_atomic(oid,admin,'audit-partial-delivered',20,'[AUDIT rollback] Partial delivered refund',false);
     IF NOT coalesce((result->>'success')::boolean,false) OR (SELECT status::text FROM public.orders WHERE id=oid)<>'delivered' THEN RAISE EXCEPTION 'partial refund changed delivered state'; END IF;
   END IF;
   result:=public.hg_refund_order_atomic(oid,admin,'audit-full-refund',CASE WHEN i=1 THEN 30 ELSE 50 END,'[AUDIT rollback] Remaining refund',false);
   IF NOT coalesce((result->>'success')::boolean,false) OR (SELECT attached_order_id FROM public.reward_redemptions WHERE id=redemption) IS DISTINCT FROM oid THEN RAISE EXCEPTION 'post-handover refund restored consumed reward'; END IF;
   result:=public.hg_refund_order_atomic(oid,admin,'audit-full-refund',CASE WHEN i=1 THEN 30 ELSE 50 END,'[AUDIT rollback] Retry refund',false);
   IF NOT coalesce((result->>'idempotent')::boolean,false) THEN RAISE EXCEPTION 'refund replay failed'; END IF;
 END LOOP;
 IF (SELECT balance FROM public.wallets WHERE user_id=customer)<>5000 OR (SELECT hp_balance FROM public.profiles WHERE id=customer)<>9700 THEN RAISE EXCEPTION 'money or earned-entitlement HP conservation failed'; END IF;
END $audit$;
ROLLBACK;
SELECT 'physical reward checkout, kitchen prep/staging/handoff, rider isolation/pickup/delivery, attempted-unclaimed, partial/full/replayed refund and early claim release passed; fixtures rolled back' as evidence;
