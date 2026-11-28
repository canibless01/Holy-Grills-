-- Squad + earned physical reward + campaign + promo + order lock; no persistent fixtures.
-- All changes, including actor balances/configuration, roll back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 u uuid:=gen_random_uuid(); admin_id uuid:=gen_random_uuid(); promo uuid:=gen_random_uuid(); order_lock uuid:=gen_random_uuid(); c uuid:=gen_random_uuid(); campaign uuid:=gen_random_uuid(); receipt uuid;
 category uuid:=gen_random_uuid(); delivery uuid; hp_reward uuid; meal uuid:=gen_random_uuid(); side uuid:=gen_random_uuid(); selection uuid:=gen_random_uuid();
 reward uuid:=gen_random_uuid(); redemption uuid; free_line jsonb; config jsonb; result jsonb; line jsonb; order_id uuid; expiry text; sides_before integer; hp_before integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Gift campaign','audit-gift-campaign-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES
 (u,'audit-benefit-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Benefits"}'),
 (admin_id,'audit-benefit-'||admin_id||'@example.invalid','{"full_name":"[AUDIT rollback] Benefits admin"}');
 UPDATE public.profiles SET campus_id=c,role='student',hp_balance=10000,next_order_hp_multiplier=1,next_order_free_delivery_cap=0 WHERE id=u;
 UPDATE public.profiles SET campus_id=c,role='admin' WHERE id=admin_id;
 INSERT INTO public.wallets(user_id,balance,currency,campus_id) VALUES(u,5000,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=5000;
 INSERT INTO public.promo_codes(id,code,discount_type,discount_value,campus_id,max_uses,max_uses_per_user)
 VALUES(promo,'AUDIT-'||promo,'flat',10,c,1,1);
 INSERT INTO public.order_locks(id,user_id,locked_date,discount_pct,status,reward_type,campus_id)
 VALUES(order_lock,u,(now() AT TIME ZONE 'Africa/Lagos')::date,10,'active','discount',c);
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
 INSERT INTO public.rewards(id,name,hp_cost,reward_type,stock_quantity,max_per_user,campus_id,metadata)
 VALUES(reward,'[AUDIT rollback] Earned extra',100,'food',2,2,c,jsonb_build_object('menu_item_id',meal));
 result:=public.hg_redeem_reward(u,reward);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'physical grant failed: %',result;END IF;
 redemption:=(result->>'redemption_id')::uuid;
 UPDATE public.reward_redemptions SET delivery_mode='next_order' WHERE id=redemption;
 UPDATE public.rewards SET is_active=false,hp_cost=900,name='[AUDIT rollback] Changed catalogue' WHERE id=reward;
 free_line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Earned extra','quantity',1,
  'price_snapshot',0,'line_total',0,'hp_earn_snapshot',0,'hp_multiplier_snapshot',1,'is_addon',false,
  'selected_variations','[]'::jsonb,'_reward_claims',jsonb_build_array(redemption),
  'options_snapshot',jsonb_build_object('reward_redemption_id',redemption,'reward_name','[AUDIT rollback] Earned extra','reward_type','food'));
 INSERT INTO public.free_side_items(id,name,campus_id) VALUES(side,'[AUDIT rollback] Side',c);
 INSERT INTO public.cart_free_side_selections(id,user_id,free_side_item_id,campus_id) VALUES(selection,u,side,c);
 SELECT coalesce(sum(credits_remaining),0) INTO sides_before FROM public.free_side_credits
   WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now();
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,
   'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,
   'selected_variations','[]'::jsonb,'options_snapshot','{}'::jsonb,
   '_reward_claims',jsonb_build_array(redemption),'_promo_discount_amount',10,'_order_lock_discount_applied',10,
   '_delivery_benefit',jsonb_build_object('source','spin','receipt_id',delivery,'cap',150,'original_fee',200,'discount',100),
   '_hp_bonus_plan',jsonb_build_object('source','spin','receipt_id',hp_reward,'multiplier',2),
   '_free_sides',jsonb_build_array(jsonb_build_object('selection_id',selection,'free_side_item_id',side,'name','[AUDIT rollback] Side')));
 result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,
   p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>100,p_discount_amount=>25,p_total_amount=>175,
   p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,p_delivery_location_lon=>null,
   p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>'[AUDIT rollback] Squad',p_notes=>'[AUDIT rollback] Gift checkout',
   p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>promo,p_order_lock_id=>order_lock,p_items=>jsonb_build_array(line,jsonb_set(free_line,'{name_snapshot}','"Forged physical reward"')),p_wallet_amount_used=>175,p_campus_id=>c,p_is_squad_order=>true,p_squad_discount_amount=>5,p_squad_item_count=>1);
 IF result->>'error' IS NULL OR (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0
 OR (SELECT status FROM public.order_locks WHERE id=order_lock)<>'active'
 OR EXISTS(SELECT 1 FROM public.reward_redemptions WHERE id=redemption AND attached_order_id IS NOT NULL)
 OR EXISTS(SELECT 1 FROM public.exclusive_spin_fulfillments WHERE id IN(delivery,hp_reward) AND applied_order_id IS NOT NULL)
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before
 THEN RAISE EXCEPTION 'rejected reward checkout leaked a debit or benefit';END IF;
 result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,
   p_claim_token=>null,p_subtotal=>100,p_delivery_fee=>100,p_discount_amount=>25,p_total_amount=>175,
   p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,p_delivery_location_lon=>null,
   p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,p_squad_name=>'[AUDIT rollback] Squad',p_notes=>'[AUDIT rollback] Gift checkout',
   p_idempotency_key=>gen_random_uuid()::text,p_promo_code_id=>promo,p_order_lock_id=>order_lock,p_items=>jsonb_build_array(line,free_line),p_wallet_amount_used=>175,p_campus_id=>c,p_is_squad_order=>true,p_squad_discount_amount=>5,p_squad_item_count=>1);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'gift checkout failed: %',result; END IF;
 order_id:=(result->>'order_id')::uuid;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>4825
 OR (SELECT applied_order_id FROM public.exclusive_spin_fulfillments WHERE id=delivery) IS DISTINCT FROM order_id
 OR (SELECT applied_order_id FROM public.exclusive_spin_fulfillments WHERE id=hp_reward) IS DISTINCT FROM order_id
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before-1
 THEN RAISE EXCEPTION 'gift reservations or side consumption failed'; END IF;
 -- A partial refund returns only money; every reserved benefit stays attached.
 result:=public.hg_refund_order_atomic(order_id,admin_id,'partial',30,'[AUDIT rollback] Partial',false);
 IF NOT coalesce((result->>'success')::boolean,false)
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>4855
 OR (SELECT status::text FROM public.orders WHERE id=order_id)<>'received'
 OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>1
 OR (SELECT status FROM public.order_locks WHERE id=order_lock)<>'used'
 OR EXISTS(SELECT 1 FROM public.exclusive_spin_fulfillments WHERE id IN(delivery,hp_reward) AND applied_order_id IS DISTINCT FROM order_id)
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before-1
 THEN RAISE EXCEPTION 'partial refund released a reserved benefit: %',result; END IF;
 result:=public.hg_refund_order_atomic(order_id,admin_id,'partial',30,'[AUDIT rollback] Lost-response retry',false);
 IF NOT coalesce((result->>'idempotent')::boolean,false) OR (SELECT balance FROM public.wallets WHERE user_id=u)<>4855
 THEN RAISE EXCEPTION 'partial refund retry duplicated credit'; END IF;
 -- Changing campaign settings must not change already-earned restoration amounts/expiry.
 UPDATE public.system_settings SET value=jsonb_set(config,'{enabled}','false') WHERE key='order_gift_campaign' AND campus_id=c;
 result:=public.hg_refund_order_atomic(order_id,u,'customer-cancel',null,'[AUDIT rollback] Cancel gift checkout',true);
 IF NOT coalesce((result->>'success')::boolean,false) OR (result->>'refund_amount')::numeric<>145 THEN RAISE EXCEPTION 'gift remainder refund failed: %',result; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>hp_before-50
 OR EXISTS(SELECT 1 FROM public.exclusive_spin_fulfillments WHERE id IN(delivery,hp_reward) AND (status<>'pending' OR applied_order_id IS NOT NULL OR result_snapshot->>'expires_at'<>expiry))
 OR (SELECT coalesce(sum(credits_remaining),0) FROM public.free_side_credits WHERE user_id=u AND (campus_id=c OR campus_id IS NULL) AND expires_at>now())<>sides_before
 THEN RAISE EXCEPTION 'refund failed to restore benefits or changed original expiry'; END IF;
 result:=public.hg_refund_order_atomic(order_id,u,'customer-cancel',null,'[AUDIT rollback] Retry cancellation',true);
 IF NOT coalesce((result->>'idempotent')::boolean,false) OR (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 THEN RAISE EXCEPTION 'refund replay changed money'; END IF;
 IF (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0
 OR (SELECT status FROM public.order_locks WHERE id=order_lock)<>'active'
 OR (SELECT ol.order_id FROM public.order_locks ol WHERE ol.id=order_lock) IS NOT NULL
 OR (SELECT coalesce(sum(amount),0) FROM public.wallet_transactions WHERE user_id=u AND reference_id=order_id AND reference_type='refund' AND type='credit')<>175
 THEN RAISE EXCEPTION 'final cancellation failed quota/lock/money conservation'; END IF;
 IF EXISTS(SELECT 1 FROM public.reward_redemptions WHERE id=redemption AND (attached_order_id IS NOT NULL OR used_at IS NOT NULL))
 OR (SELECT reward_snapshot->>'name' FROM public.reward_redemptions WHERE id=redemption)<>'[AUDIT rollback] Earned extra'
 OR (SELECT stock_quantity FROM public.rewards WHERE id=reward)<>1
 OR NOT EXISTS(SELECT 1 FROM public.orders WHERE id=order_id AND is_squad_order AND squad_discount_amount=5)
 THEN RAISE EXCEPTION 'squad/earned benefit restoration lost promise, stock or discount';END IF;
 -- A different retry intent must also leave every restored credit unchanged.
 result:=public.hg_refund_order_atomic(order_id,u,'another-cancel',null,'[AUDIT rollback] New retry key',true);
 IF NOT coalesce((result->>'idempotent')::boolean,false)
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>5000
 OR (SELECT credits_remaining FROM public.free_side_credits WHERE id=md5(receipt::text||':free_side')::uuid)<>2
 OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0
 THEN RAISE EXCEPTION 'different retry key duplicated restoration'; END IF;
END $audit$;
ROLLBACK;
SELECT 'passed: squad discount + frozen earned physical reward + campaign sides/delivery/HP reservation + promo + order lock; partial refund, replay, changed configuration, final cancellation and second-intent conservation; all fixtures rolled back' AS evidence;
