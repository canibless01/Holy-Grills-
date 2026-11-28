-- Financial/lifecycle evidence on real Postgres, with every fixture rolled back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[]; ambassador uuid; actor uuid; customer uuid; other uuid;
 campus uuid:=gen_random_uuid(); category uuid:=gen_random_uuid(); meal uuid:=gen_random_uuid();
 grant_result jsonb; result jsonb; line jsonb; discount uuid; oid uuid; second_order uuid;
 promo uuid:=gen_random_uuid(); intent text:=gen_random_uuid()::text; hp_before integer; hits integer; code text;
BEGIN
 ids:=ARRAY[gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid()];
 INSERT INTO auth.users(id,email,raw_user_meta_data)
 SELECT id, 'audit-amb-recovery-'||id||'@example.invalid', '{"full_name":"Audit rollback ambassador"}'::jsonb FROM unnest(ids) id;
 INSERT INTO public.wallets(user_id,balance) SELECT id,5000 FROM unnest(ids) id ON CONFLICT(user_id) DO UPDATE SET balance=5000;
 ambassador:=ids[1];actor:=ids[2];customer:=ids[3];other:=ids[4];
 INSERT INTO public.campuses(id,name,slug) VALUES(campus,'[AUDIT rollback] Ambassador','audit-amb-'||campus);
 UPDATE public.profiles SET campus_id=campus WHERE id=ANY(ids);
 UPDATE public.profiles SET role='super_admin' WHERE id=actor;
 UPDATE public.wallets SET balance=5000 WHERE user_id=ANY(ids);
 code:='AUDIT'||upper(replace(ambassador::text,'-',''));
 UPDATE public.profiles SET referral_code=code WHERE id=ambassador;
 UPDATE public.profiles SET referral_code='AUDIT'||upper(replace(other::text,'-','')) WHERE id=other;
 INSERT INTO public.ambassadors(profile_id,campus_id,tagged_by) VALUES(ambassador,campus,actor),(other,campus,actor)
 ON CONFLICT(profile_id) DO UPDATE SET status='active',campus_id=excluded.campus_id;
 SELECT hp_balance INTO hp_before FROM public.profiles WHERE id=ambassador;
 grant_result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'hp',50,'2026-10','[AUDIT rollback] HP',14,1,'manual',null,false,intent);
 IF grant_result->>'id' IS NULL OR (SELECT hp_balance FROM public.profiles WHERE id=ambassador)<>hp_before+50 THEN RAISE EXCEPTION 'HP grant failed: %',grant_result; END IF;
 result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'hp',50,'2026-10','[AUDIT rollback] HP',14,1,'manual',null,false,intent);
 IF result->>'id'<>grant_result->>'id' OR NOT (result->>'idempotent')::boolean OR (SELECT hp_balance FROM public.profiles WHERE id=ambassador)<>hp_before+50 THEN RAISE EXCEPTION 'HP replay changed award'; END IF;
 result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'hp',100,'2026-10','[AUDIT rollback] Duplicate',14,1,'manual',null,false,gen_random_uuid()::text);
 IF result->>'error'<>'duplicate_monthly_grant' THEN RAISE EXCEPTION 'monthly duplicate allowed'; END IF;
 result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'free_side',2,'2026-10','[AUDIT rollback] Sides',30,1,'manual',null,false,gen_random_uuid()::text);
 IF (SELECT credits_remaining FROM public.free_side_credits WHERE id=(result->>'free_side_grant_id')::uuid)<>2 THEN RAISE EXCEPTION 'side grant missing'; END IF;
 grant_result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'meal_discount',75,'2026-10','[AUDIT rollback] Meal',14,1,'manual',null,false,gen_random_uuid()::text);
 discount:=(grant_result->>'meal_discount_id')::uuid;
 IF discount IS NULL THEN RAISE EXCEPTION 'discount grant missing'; END IF;
 -- Invalid claim fails after award work, and must roll back both award and grant.
 BEGIN
   PERFORM public.hg_issue_ambassador_grant_atomic(actor,ambassador,'hp',25,'2026-10','[AUDIT rollback] Invalid claim',14,1,'milestone',gen_random_uuid(),true,gen_random_uuid()::text);
   RAISE EXCEPTION 'invalid claim accepted';
 EXCEPTION WHEN foreign_key_violation OR raise_exception THEN
   IF SQLERRM='invalid claim accepted' THEN RAISE; END IF;
 END;
 IF (SELECT hp_balance FROM public.profiles WHERE id=ambassador)<>hp_before+50 THEN RAISE EXCEPTION 'partial HP grant leaked'; END IF;
 INSERT INTO public.promo_codes(id,code,discount_type,discount_value,campus_id,max_uses,max_uses_per_user) VALUES(promo,'AUDIT-'||promo,'flat',10,campus,1,1);
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Ambassador','audit-amb-'||category,campus);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id) VALUES(meal,category,'[AUDIT rollback] Meal','audit-amb-'||meal,100,10,campus);
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,'price_snapshot',100,'line_total',100,
   'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,'options_snapshot','{}'::jsonb,'selected_variations','[]'::jsonb,
   '_promo_discount_amount',10,'_ambassador_meal_discount',jsonb_build_object('discount_id',discount,'amount',75,'meal_item_id',meal));
 intent:=gen_random_uuid()::text;
 result:=public.hg_create_order_atomic(p_user_id=>ambassador,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>100,p_delivery_fee=>20,p_discount_amount=>85,p_total_amount=>35,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,
   p_notes=>'[AUDIT rollback]',p_idempotency_key=>intent,p_promo_code_id=>promo,p_items=>jsonb_build_array(line),p_wallet_amount_used=>35,p_campus_id=>campus);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'meal checkout failed: %',result; END IF;
 oid:=(result->>'order_id')::uuid;
 IF (SELECT discount_amount FROM public.promo_code_uses WHERE order_id=oid) IS DISTINCT FROM 10::numeric THEN RAISE EXCEPTION 'promo usage counted another benefit as promo discount'; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=ambassador)<>4965 OR (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>0
 OR (SELECT ambassador_discount_id FROM public.orders WHERE id=oid) IS DISTINCT FROM discount THEN RAISE EXCEPTION 'discount/charge did not commit together'; END IF;
 -- Last use already consumed: a second admission must roll back the whole new order.
 result:=public.hg_create_order_atomic(p_user_id=>ambassador,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>100,p_delivery_fee=>20,p_discount_amount=>85,p_total_amount=>35,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,
   p_notes=>'[AUDIT rollback]',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>promo,p_items=>jsonb_build_array(line),p_wallet_amount_used=>35,p_campus_id=>campus);
 IF result->>'error' IS NULL OR (SELECT balance FROM public.wallets WHERE user_id=ambassador)<>4965
 OR (SELECT count(*) FROM public.orders WHERE campus_id=campus)<>1 THEN RAISE EXCEPTION 'duplicate discounted checkout leaked order or debit'; END IF;
 IF result->>'error' IS DISTINCT FROM 'promo_unavailable' THEN RAISE EXCEPTION 'global promo limit not enforced'; END IF;
 UPDATE public.promo_codes SET max_uses=null WHERE id=promo;
 result:=public.hg_create_order_atomic(p_user_id=>ambassador,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>100,p_delivery_fee=>20,p_discount_amount=>85,p_total_amount=>35,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,
   p_notes=>'[AUDIT rollback]',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>promo,p_items=>jsonb_build_array(line),p_wallet_amount_used=>35,p_campus_id=>campus);
 IF result->>'error' IS DISTINCT FROM 'promo_unavailable' THEN RAISE EXCEPTION 'per-user promo limit not enforced'; END IF;
 UPDATE public.promo_codes SET max_uses=1 WHERE id=promo;
 result:=public.hg_refund_order_atomic(oid,ambassador,'audit-cancel',null,'[AUDIT rollback]',true);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'meal cancellation failed: %',result; END IF;
 IF (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0 THEN RAISE EXCEPTION 'cancel did not release promo use'; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=ambassador)<>5000 OR (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>1 THEN RAISE EXCEPTION 'cancel did not restore wallet and meal use'; END IF;
 result:=public.hg_refund_order_atomic(oid,ambassador,'audit-cancel',null,'[AUDIT rollback]',true);
 IF (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>1 THEN RAISE EXCEPTION 'cancel replay refilled twice'; END IF;
 UPDATE public.promo_codes SET used_count=1 WHERE id=promo; -- historical cancelled-use counter
 result:=public.hg_create_order_atomic(p_user_id=>ambassador,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>100,p_delivery_fee=>20,p_discount_amount=>85,p_total_amount=>35,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,
   p_notes=>'[AUDIT rollback]',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>promo,p_items=>jsonb_build_array(line),p_wallet_amount_used=>35,p_campus_id=>campus);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'restored discount could not be reused: %',result; END IF;
 second_order:=(result->>'order_id')::uuid;
 UPDATE public.orders SET status='preparing' WHERE id=second_order;
 result:=public.hg_refund_order_atomic(second_order,actor,'audit-partial-post-prep',10,'[AUDIT rollback]',false);
 IF NOT coalesce((result->>'success')::boolean,false) OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>1 THEN RAISE EXCEPTION 'partial refund released promo'; END IF;
 result:=public.hg_refund_order_atomic(second_order,actor,'audit-post-prep-refund',25,'[AUDIT rollback]',false);
 IF NOT coalesce((result->>'success')::boolean,false) OR (SELECT balance FROM public.wallets WHERE user_id=ambassador)<>5000
 OR (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>0 THEN RAISE EXCEPTION 'post-prep refund restored a spent meal benefit or lost money: %',result; END IF;
 IF (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0 THEN RAISE EXCEPTION 'full refund did not release promo use or replay double released'; END IF;
 -- Tracking: anonymous adoption is idempotent, and future clicks cannot steal an earlier order.
 result:=public.hg_ambassador_record_click(code,null,'audit-'||intent,campus);
 result:=public.hg_ambassador_merge_visitor('audit-'||intent,customer);
 SELECT click_count INTO hits FROM public.ambassador_attributions WHERE customer_user_id=customer;
 result:=public.hg_ambassador_merge_visitor('audit-'||intent,customer);
 IF (result->>'adopted_clicks')::int<>0 OR (SELECT click_count FROM public.ambassador_attributions WHERE customer_user_id=customer)<>hits THEN RAISE EXCEPTION 'merge replay changed attribution counters'; END IF;
 UPDATE public.ambassador_link_clicks SET created_at=now()-interval '1 day' WHERE anonymous_id='audit-'||intent;
 INSERT INTO public.orders(id,user_id,campus_id,subtotal,delivery_fee,total_amount,status,payment_status,created_at)
 VALUES(gen_random_uuid(),customer,campus,100,0,100,'delivered','paid',now()-interval '1 hour') RETURNING id INTO second_order;
 result:=public.hg_ambassador_record_click('AUDIT'||upper(replace(other::text,'-','')),customer,null,campus);
 result:=public.hg_ambassador_attribute_order(second_order);
 IF (SELECT ambassador_id FROM public.ambassador_order_attributions WHERE order_id=second_order) IS DISTINCT FROM ambassador THEN RAISE EXCEPTION 'historical order attribution failed: %, window=%, clicks=%, order=%',result,public.hg_ambassador_window_days(),(SELECT jsonb_agg(jsonb_build_object('ambassador_match',ambassador_id=ambassador,'created_at',created_at)) FROM public.ambassador_link_clicks WHERE visitor_user_id=customer),(SELECT jsonb_build_object('created_at',created_at,'status',status,'payment_status',payment_status) FROM public.orders WHERE id=second_order); END IF;
 result:=public.hg_ambassador_attribute_order(second_order);
 IF (SELECT count(*) FROM public.ambassador_order_attributions WHERE order_id=second_order)<>1 THEN RAISE EXCEPTION 'delivered order counted twice'; END IF;
 result:=public.hg_ambassador_record_click(code,ambassador,null,campus);
 IF result->>'reason'<>'self_click' THEN RAISE EXCEPTION 'self attribution allowed'; END IF;

 -- Cancellation releases a reserved use but cannot revive a voided benefit.
 grant_result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'meal_discount',75,'2026-10','[AUDIT rollback] Void restoration',14,2,'manual',null,true,gen_random_uuid()::text);
 discount:=(grant_result->>'meal_discount_id')::uuid;
 INSERT INTO public.orders(id,user_id,campus_id,subtotal,delivery_fee,total_amount,status,payment_status)
 VALUES(gen_random_uuid(),ambassador,campus,100,20,45,'received','pending') RETURNING id INTO oid;
 result:=public.hg_redeem_ambassador_meal_discount(discount,oid,ambassador,75,meal);
 IF (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>1 THEN RAISE EXCEPTION 'multi-use redemption did not spend exactly one'; END IF;
 UPDATE public.ambassador_meal_discounts SET status='voided' WHERE id=discount;
 result:=public.hg_restore_ambassador_meal_discount(oid);
 IF (SELECT status FROM public.ambassador_meal_discounts WHERE id=discount)<>'voided'
 OR (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>2 THEN RAISE EXCEPTION 'cancellation revived a voided benefit'; END IF;
 result:=public.hg_restore_ambassador_meal_discount(oid);
 IF (result->>'restored')::boolean OR (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>2 THEN RAISE EXCEPTION 'restore replay increased uses'; END IF;
 -- Expiry is checked under lock without a global sweep.
 UPDATE public.ambassador_meal_discounts SET status='active',expires_at=now()-interval '1 second' WHERE id=discount;
 BEGIN
   PERFORM public.hg_redeem_ambassador_meal_discount(discount,gen_random_uuid(),ambassador,75,meal);
   RAISE EXCEPTION 'expired reward accepted';
 EXCEPTION WHEN check_violation THEN NULL; END;
 -- A foreign owner cannot reserve a use; invalid amounts do not mutate one.
 UPDATE public.ambassador_meal_discounts SET expires_at=now()+interval '1 day' WHERE id=discount;
 BEGIN
   PERFORM public.hg_redeem_ambassador_meal_discount(discount,gen_random_uuid(),other,75,meal);
   RAISE EXCEPTION 'foreign reward accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN
   PERFORM public.hg_redeem_ambassador_meal_discount(discount,gen_random_uuid(),ambassador,76,meal);
   RAISE EXCEPTION 'over-cap reward accepted';
 EXCEPTION WHEN check_violation THEN NULL; END;
 IF (SELECT uses_remaining FROM public.ambassador_meal_discounts WHERE id=discount)<>2 THEN RAISE EXCEPTION 'failed claim spent a use'; END IF;
 IF has_function_privilege('anon','public.hg_redeem_ambassador_meal_discount(uuid,uuid,uuid,numeric,uuid)','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_restore_ambassador_meal_discount(uuid)','EXECUTE') THEN RAISE EXCEPTION 'financial helper publicly callable'; END IF;


 -- A more expensive meal stays orderable: customer pays the difference plus delivery.
 grant_result:=public.hg_issue_ambassador_grant_atomic(actor,ambassador,'meal_discount',3000,'2026-10','[AUDIT rollback] Top-up meal',14,1,'manual',null,true,gen_random_uuid()::text);
 discount:=(grant_result->>'meal_discount_id')::uuid;
 UPDATE public.menu_items SET price=4500 WHERE id=meal;
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,'price_snapshot',4500,'line_total',4500,
   'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,'options_snapshot','{}'::jsonb,'selected_variations','[]'::jsonb,
   '_promo_discount_amount',0,'_ambassador_meal_discount',jsonb_build_object('discount_id',discount,'amount',3000,'meal_item_id',meal));
 result:=public.hg_create_order_atomic(p_user_id=>ambassador,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,p_claim_token=>null,
   p_subtotal=>4500,p_delivery_fee=>500,p_discount_amount=>3000,p_total_amount=>2000,p_delivery_type=>'off_campus',p_delivery_location_id=>null,
   p_delivery_location_lat=>null,p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,
   p_notes=>'[AUDIT rollback]',p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>2000,p_campus_id=>campus);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'higher-priced meal was restricted: %',result; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.orders WHERE id=(result->>'order_id')::uuid AND total_amount=2000 AND delivery_fee=500 AND discount_amount=3000)
    OR (SELECT balance FROM public.wallets WHERE user_id=ambassador)<>3000 THEN RAISE EXCEPTION 'meal difference/delivery payment is incorrect'; END IF;

END $audit$;
ROLLBACK;
SELECT 'ambassador grants, checkout, refund, retries and historical attribution passed; all fixtures rolled back' as evidence;
