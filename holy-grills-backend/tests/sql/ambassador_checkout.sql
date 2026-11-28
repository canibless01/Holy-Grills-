-- Financial/lifecycle evidence on real Postgres, with every fixture rolled back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[]; ambassador uuid; actor uuid; customer uuid; other uuid;
 campus uuid:=gen_random_uuid(); category uuid:=gen_random_uuid(); meal uuid:=gen_random_uuid();
 grant_result jsonb; result jsonb; line jsonb; discount uuid; oid uuid; second_order uuid;
 promo uuid:=gen_random_uuid(); intent text:=gen_random_uuid()::text; hp_before integer; hits integer; code text;
BEGIN
 SELECT array_agg(id) INTO ids FROM (SELECT p.id FROM public.profiles p JOIN public.wallets w ON w.user_id=p.id
   WHERE p.full_name ILIKE '%audit%' AND p.is_active ORDER BY p.id LIMIT 4) selected;
 IF cardinality(ids)<4 THEN RAISE EXCEPTION 'four isolated audit identities required'; END IF;
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
END $audit$;
ROLLBACK;
SELECT 'ambassador grants, checkout, refund, retries and historical attribution passed; all fixtures rolled back' as evidence;
