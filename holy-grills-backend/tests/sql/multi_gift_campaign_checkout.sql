-- Full gift bundle -> existing checkout reservations -> pre-preparation refund.
-- All changes, including actor balances/configuration, roll back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 u uuid; c uuid:=gen_random_uuid(); campaign uuid:=gen_random_uuid(); receipt uuid;
 category uuid:=gen_random_uuid(); delivery uuid; hp_reward uuid; meal uuid:=gen_random_uuid(); side uuid:=gen_random_uuid(); selection uuid:=gen_random_uuid();
 config jsonb; expired_receipt uuid; expected_error text; result jsonb; line jsonb; order_id uuid; expiry text; signup_start timestamptz; sides_before integer; hp_before integer;
BEGIN
 SELECT p.id INTO u FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id
 WHERE p.role::text='student' AND p.is_active AND p.full_name ILIKE '%audit%' AND c.name ILIKE '%audit%'
 AND NOT EXISTS(SELECT 1 FROM public.cart_free_side_selections s WHERE s.user_id=p.id) LIMIT 1;
 IF u IS NULL THEN RAISE EXCEPTION 'isolated student with no existing free-side cart required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Gift campaign','audit-gift-campaign-'||c);
 UPDATE public.profiles SET campus_id=c,next_order_hp_multiplier=1,next_order_free_delivery_cap=0 WHERE id=u;
 UPDATE public.wallets SET balance=5000 WHERE user_id=u;
 IF NOT FOUND THEN RAISE EXCEPTION 'existing audit wallet required'; END IF;
 SELECT hp_balance INTO hp_before FROM public.profiles WHERE id=u;
 config:=jsonb_build_object('id',campaign,'name','[AUDIT rollback] Launch bundle','enabled',true,
   'eligibility','everyone','starts_at',now()-interval '1 day','ends_at',now()+interval '1 day','validity_days',60,
   'benefits',jsonb_build_array(
      jsonb_build_object('kind','hp','amount',50,'label','50 HP'),
      jsonb_build_object('kind','free_side','credits',2,'label','2 side credits'),
      jsonb_build_object('kind','delivery_discount','percent',50,'cap',150,'label','50% off delivery'),
      jsonb_build_object('kind','hp_multiplier','multiplier',2,'label','2x food HP')));
 INSERT INTO public.system_settings(key,value,campus_id,is_public) VALUES('order_gift_campaign',config,c,true);
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF NOT coalesce((result->>'granted')::boolean,false) THEN RAISE EXCEPTION 'bundle grant failed: %',result; END IF;
 receipt:=(result->>'receipt_id')::uuid; expiry:=result->>'expires_at';
 delivery:=md5(receipt::text||':delivery_discount')::uuid; hp_reward:=md5(receipt::text||':hp_multiplier')::uuid;
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before+50
 OR (SELECT credits_remaining FROM public.free_side_credits WHERE id=md5(receipt::text||':free_side')::uuid)<>2
 OR (SELECT count(*) FROM public.exclusive_spin_fulfillments WHERE user_id=u AND result_snapshot->>'campaign_id'=campaign::text)<>3
 THEN RAISE EXCEPTION 'bundle components missing or not immediate'; END IF;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF NOT coalesce((result->>'idempotent')::boolean,false) OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before+50
 THEN RAISE EXCEPTION 'claim retry refilled gifts'; END IF;
 UPDATE public.system_settings SET value=jsonb_set(config,'{name}','"Changed campaign name"') WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'name'<>'[AUDIT rollback] Launch bundle' THEN RAISE EXCEPTION 'earned bundle changed with configuration'; END IF;
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Campaign category','audit-campaign-'||category,c);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id) VALUES(meal,category,'[AUDIT rollback] Meal','audit-campaign-meal-'||meal,100,10,c);
 INSERT INTO public.free_side_items(id,name,campus_id) VALUES(side,'[AUDIT rollback] Side',c);
 INSERT INTO public.cart_free_side_selections(id,user_id,free_side_item_id,campus_id) VALUES(selection,u,side,c);
 SELECT coalesce(sum(credits_remaining),0) INTO sides_before FROM public.free_side_credits
   WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now();
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,
   'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,
   'selected_variations','[]'::jsonb,'options_snapshot','{}'::jsonb,
   '_delivery_benefit',jsonb_build_object('source','spin','receipt_id',delivery,'cap',150,'original_fee',200,'discount',100),
   '_hp_bonus_plan',jsonb_build_object('source','spin','receipt_id',hp_reward,'multiplier',2),
   '_free_sides',jsonb_build_array(jsonb_build_object('selection_id',selection,'free_side_item_id',side,'name','[AUDIT rollback] Side')));
 result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,
   p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>100,p_discount_amount=>0,p_total_amount=>200,
   p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,p_delivery_location_lon=>null,
   p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,p_notes=>'[AUDIT rollback] Gift checkout',
   p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>200,p_campus_id=>c);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'gift checkout failed: %',result; END IF;
 order_id:=(result->>'order_id')::uuid;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>4800
 OR (SELECT applied_order_id FROM public.exclusive_spin_fulfillments WHERE id=delivery) IS DISTINCT FROM order_id
 OR (SELECT applied_order_id FROM public.exclusive_spin_fulfillments WHERE id=hp_reward) IS DISTINCT FROM order_id
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before-1
 THEN RAISE EXCEPTION 'gift reservations or side consumption failed'; END IF;
 result:=public.hg_refund_order_atomic(order_id,u,'customer-cancel',null,'[AUDIT rollback] Cancel gift checkout',true);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'gift refund failed: %',result; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before+50
 OR EXISTS(SELECT 1 FROM public.exclusive_spin_fulfillments WHERE id IN(delivery,hp_reward) AND (status<>'pending' OR applied_order_id IS NOT NULL OR result_snapshot->>'expires_at'<>expiry))
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before
 THEN RAISE EXCEPTION 'refund failed to restore benefits or changed original expiry'; END IF;
 result:=public.hg_refund_order_atomic(order_id,u,'customer-cancel',null,'[AUDIT rollback] Retry cancellation',true);
 IF NOT coalesce((result->>'idempotent')::boolean,false) OR (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 THEN RAISE EXCEPTION 'refund replay changed money'; END IF;
 -- Expiry is checked again under the order lock, after any earlier quote.
 FOREACH expired_receipt IN ARRAY ARRAY[delivery,hp_reward] LOOP
   expected_error:=CASE WHEN expired_receipt=delivery THEN 'delivery_benefit_changed' ELSE 'hp_bonus_changed' END;
   UPDATE public.exclusive_spin_fulfillments SET result_snapshot=jsonb_set(result_snapshot,'{expires_at}',to_jsonb(now()-interval '1 minute')) WHERE id=expired_receipt;
   BEGIN
 result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,
   p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>100,p_discount_amount=>0,p_total_amount=>200,
   p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,p_delivery_location_lon=>null,
   p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>null,p_notes=>'[AUDIT rollback] Gift checkout',
   p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>null,p_items=>jsonb_build_array(line),p_wallet_amount_used=>200,p_campus_id=>c);
     IF result->>'error' IS DISTINCT FROM expected_error THEN RAISE EXCEPTION 'expired benefit refusal incorrect: %',result; END IF;
   END;
   UPDATE public.exclusive_spin_fulfillments SET result_snapshot=jsonb_set(result_snapshot,'{expires_at}',to_jsonb(expiry)) WHERE id=expired_receipt;
 END LOOP;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>5000 THEN RAISE EXCEPTION 'refused expired benefit still charged wallet'; END IF;
 -- An invalid later component must not leave the earlier HP component granted.
 campaign:=gen_random_uuid(); config:=jsonb_set(config,'{id}',to_jsonb(campaign));
 config:=jsonb_set(config,'{benefits}',jsonb_build_array(jsonb_build_object('kind','hp','amount',100,'label','100 HP'),jsonb_build_object('kind','exclusive_spin','label','Forbidden spin')));
 UPDATE public.system_settings SET value=config WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF NOT result ? 'error' OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before+50
 THEN RAISE EXCEPTION 'invalid bundle left a partial grant'; END IF;
 -- Eligibility and campaign windows are enforced by the grant, not only the UI.
 campaign:=gen_random_uuid();
 config:=jsonb_build_object('id',campaign,'name','[AUDIT rollback] Eligibility','enabled',true,
   'eligibility','first_order','starts_at',now()-interval '1 day','ends_at',now()+interval '1 day',
   'validity_days',60,'benefits',jsonb_build_array(jsonb_build_object('kind','hp','amount',1,'label','1 HP')));
 INSERT INTO public.orders(user_id,campus_id,payment_status,delivery_type,created_at)
 VALUES(u,c,'paid','off_campus',now()-interval '2 days'),(u,c,'paid','off_campus',now()-interval '2 days');
 UPDATE public.system_settings SET value=config WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'reason'<>'account_ineligible' THEN RAISE EXCEPTION 'earlier paid customers qualified for first-order campaign'; END IF;
 SELECT created_at+(now()-created_at)/2 INTO signup_start FROM auth.users WHERE id=u;
 config:=jsonb_set(jsonb_set(config,'{eligibility}','"signup"'),'{starts_at}',to_jsonb(signup_start));
 UPDATE public.system_settings SET value=config WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'reason'<>'account_ineligible' THEN RAISE EXCEPTION 'pre-campaign account qualified for signup campaign'; END IF;
 config:=jsonb_set(jsonb_set(jsonb_set(config,'{eligibility}','"everyone"'),'{starts_at}',to_jsonb(now()+interval '1 hour')),'{ends_at}',to_jsonb(now()+interval '2 hours'));
 UPDATE public.system_settings SET value=config WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'reason'<>'upcoming' THEN RAISE EXCEPTION 'upcoming campaign granted early'; END IF;
 config:=jsonb_set(jsonb_set(config,'{starts_at}',to_jsonb(now()-interval '2 hours')),'{ends_at}',to_jsonb(now()-interval '1 hour'));
 UPDATE public.system_settings SET value=config WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'reason'<>'ended' THEN RAISE EXCEPTION 'ended campaign still granted'; END IF;
 UPDATE public.system_settings SET value=jsonb_set(config,'{enabled}','false') WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_claim_gift_campaign_atomic(u,campaign);
 IF result->>'reason'<>'disabled' THEN RAISE EXCEPTION 'paused campaign still granted'; END IF;
 result:=public.hg_claim_gift_campaign_atomic(u,gen_random_uuid());
 IF result->>'reason'<>'campaign_changed' THEN RAISE EXCEPTION 'stale claim silently used different campaign'; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before+50 THEN RAISE EXCEPTION 'refused claim altered HP'; END IF;

END;
$audit$;
SELECT 'passed' AS multi_gift_campaign_checkout_refund_checks;
ROLLBACK;
