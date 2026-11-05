-- Actual normal/flash HP redemptions and zero-value order claim. All effects roll back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 u uuid; c uuid:=gen_random_uuid(); r uuid:=gen_random_uuid(); normal_id uuid; flash_id uuid;
 result jsonb; promise jsonb; fake_line jsonb; order_result jsonb; v_order_id uuid;
BEGIN
 SELECT p.id INTO u FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id
 WHERE p.role::text='student' AND p.is_active AND p.full_name ILIKE '%audit%'
 AND c.name ILIKE '%audit%' LIMIT 1;
 IF u IS NULL THEN RAISE EXCEPTION 'isolated audit student required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Reward promise','audit-reward-promise-'||c);
 UPDATE public.profiles SET campus_id=c,hp_balance=10000 WHERE id=u;
 INSERT INTO public.rewards(id,name,hp_cost,reward_type,stock_quantity,max_per_user,campus_id,metadata)
 VALUES(r,'[AUDIT rollback] Earned meal',100,'food',5,5,c,'{"private_cost_note":"must not enter receipt"}');
 result:=public.hg_redeem_reward(u,r);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'normal redemption failed: %',result->>'error'; END IF;
 normal_id:=(result->>'redemption_id')::uuid;
 SELECT reward_snapshot INTO promise FROM public.reward_redemptions WHERE id=normal_id;
 IF promise->>'name'<>'[AUDIT rollback] Earned meal' OR promise->'metadata' ? 'private_cost_note'
 THEN RAISE EXCEPTION 'normal promise capture or public-field allowlist failed'; END IF;
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('flash_redemptions',true,c);
 INSERT INTO public.flash_redemptions(reward_id,window_starts_at,window_ends_at,quantity_limit,discount_pct,campus_id)
 VALUES(r,now()-interval '1 minute',now()+interval '1 hour',5,0.5,c);
 result:=public.hg_redeem_flash_reward_atomic(u,r);
 IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'flash redemption failed: %',result->>'error'; END IF;
 flash_id:=(result->>'redemption_id')::uuid;
 IF (SELECT reward_snapshot FROM public.reward_redemptions WHERE id=flash_id) IS DISTINCT FROM promise
 OR (SELECT hp_cost_snapshot FROM public.reward_redemptions WHERE id=flash_id)<>50
 THEN RAISE EXCEPTION 'flash promise or actual discounted HP receipt failed'; END IF;
 UPDATE public.rewards SET name='[AUDIT rollback] Replacement',metadata='{}',hp_cost=900,is_active=false WHERE id=r;
 IF (SELECT reward_snapshot FROM public.reward_redemptions WHERE id=normal_id) IS DISTINCT FROM promise
 THEN RAISE EXCEPTION 'catalog edit altered earned promise'; END IF;
 BEGIN
   UPDATE public.reward_redemptions SET reward_snapshot='{"name":"forged"}' WHERE id=normal_id;
   RAISE EXCEPTION 'snapshot mutation accepted';
 EXCEPTION WHEN check_violation THEN
   IF SQLERRM<>'reward_promise_immutable' THEN RAISE; END IF;
 END;
 BEGIN
   UPDATE public.reward_redemptions SET hp_cost_snapshot=1 WHERE id=normal_id;
   RAISE EXCEPTION 'price mutation accepted';
 EXCEPTION WHEN check_violation THEN
   IF SQLERRM<>'reward_promise_immutable' THEN RAISE; END IF;
 END;
 fake_line:=jsonb_build_object('menu_item_id',null,'name_snapshot','[AUDIT rollback] Earned meal',
   'quantity',1,'price_snapshot',0,'line_total',0,'hp_earn_snapshot',0,'hp_multiplier_snapshot',1,
   'is_addon',false,'selected_variations','[]'::jsonb,'_reward_claims',jsonb_build_array(normal_id),
   'options_snapshot',jsonb_build_object('reward_redemption_id',normal_id,
        'reward_name','[AUDIT rollback] Earned meal','reward_type','food'));
 order_result:=public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>null,p_guest_email=>null,p_guest_phone=>null,
   p_claim_token=>null,p_subtotal=>0,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>0,
   p_delivery_type=>'off_campus',p_delivery_location_id=>null,p_delivery_location_lat=>null,
   p_delivery_location_lon=>null,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>null,
   p_squad_name=>null,p_notes=>'[AUDIT rollback] Reward promise claim',p_idempotency_key=>gen_random_uuid()::text,
   p_promo_code_id=>null,p_items=>jsonb_build_array(fake_line),p_campus_id=>c,p_redemption_id=>normal_id,
   p_payment_status=>'paid');
 IF NOT coalesce((order_result->>'success')::boolean,false) THEN RAISE EXCEPTION 'frozen reward order failed: %',order_result->>'error'; END IF;
 v_order_id:=(order_result->>'order_id')::uuid;
 IF (SELECT attached_order_id FROM public.reward_redemptions WHERE id=normal_id) IS DISTINCT FROM v_order_id
 OR NOT EXISTS(SELECT 1 FROM public.order_items oi WHERE oi.order_id=v_order_id AND name_snapshot='[AUDIT rollback] Earned meal' AND price_snapshot=0)
 THEN RAISE EXCEPTION 'earned order line/claim failed'; END IF;
 UPDATE public.reward_redemptions SET attached_order_id=null,used_at=null,delivery_mode='next_order' WHERE id=normal_id;
 IF (SELECT reward_snapshot FROM public.reward_redemptions WHERE id=normal_id) IS DISTINCT FROM promise
 THEN RAISE EXCEPTION 'release damaged saved promise'; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>9850
 THEN RAISE EXCEPTION 'normal and flash HP conservation failed'; END IF;
END;
$audit$;
SELECT 'passed' AS earned_reward_promise_checks;
ROLLBACK;
