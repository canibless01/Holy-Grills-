-- Isolated compatibility proof; no live account or external provider is used.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.legacy_checkout(u uuid,c uuid,meal uuid,intent text,line jsonb,fee numeric,total numeric) RETURNS jsonb LANGUAGE sql AS $$
 SELECT public.hg_create_order_atomic(p_user_id=>u,p_guest_name=>NULL,p_guest_email=>NULL,p_guest_phone=>NULL,p_claim_token=>NULL,
 p_subtotal=>100,p_delivery_fee=>fee,p_discount_amount=>0,p_total_amount=>total,p_delivery_type=>'off_campus',p_delivery_location_id=>NULL,
 p_delivery_location_lat=>NULL,p_delivery_location_lon=>NULL,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>NULL,p_squad_name=>NULL,
 p_notes=>'[AUDIT rollback] Legacy benefit',p_idempotency_key=>intent,p_promo_code_id=>NULL,p_items=>jsonb_build_array(line),p_wallet_amount_used=>total,p_campus_id=>c)
$$;
DO $$
DECLARE c uuid:=gen_random_uuid();u uuid:=gen_random_uuid();category uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();oid uuid;converted uuid;intent text:=gen_random_uuid()::text;r jsonb;line jsonb;changed jsonb;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Legacy rewards','audit-legacy-reward-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-legacy-reward-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Legacy rewards"}');
 UPDATE profiles SET campus_id=c,role='student',next_order_hp_multiplier=2,next_order_free_delivery_cap=200 WHERE id=u;
 INSERT INTO wallets(user_id,balance,currency,campus_id) VALUES(u,5000,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=5000;
 INSERT INTO menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Legacy','audit-legacy-'||category,c);
 INSERT INTO menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id) VALUES(meal,category,'[AUDIT rollback] Meal','audit-legacy-'||meal,100,10,c);
 line:=jsonb_build_object('menu_item_id',meal,'name_snapshot','[AUDIT rollback] Meal','quantity',1,'price_snapshot',100,'line_total',100,'hp_earn_snapshot',10,'hp_multiplier_snapshot',1,'is_addon',false,'selected_variations','[]'::jsonb,'options_snapshot','{}'::jsonb,
 '_delivery_benefit',jsonb_build_object('source','legacy_spin','cap',200,'original_fee',300,'discount',200),
 '_hp_bonus_plan',jsonb_build_object('source','legacy','name','Legacy double food HP','multiplier',2));
 BEGIN PERFORM pg_temp.legacy_checkout(u,c,meal,intent,line,100,200);RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='simulate interruption';EXCEPTION WHEN no_data_found THEN NULL;END;
 IF (SELECT balance FROM wallets WHERE user_id=u)<>5000 OR (SELECT next_order_hp_multiplier FROM profiles WHERE id=u)<>2 OR (SELECT next_order_free_delivery_cap FROM profiles WHERE id=u)<>200 OR EXISTS(SELECT 1 FROM exclusive_spin_fulfillments WHERE user_id=u) THEN RAISE EXCEPTION 'interruption consumed legacy balance/benefit';END IF;
 r:=pg_temp.legacy_checkout(u,c,meal,intent,line,100,200);
 IF NOT coalesce((r->>'success')::boolean,false) THEN RAISE EXCEPTION 'legacy admission failed: %',r;END IF;
 oid:=(r->>'order_id')::uuid;
 SELECT id INTO converted FROM exclusive_spin_fulfillments WHERE user_id=u AND applied_order_id=oid AND result_snapshot->>'legacy'='true';
 IF converted IS NULL OR (SELECT next_order_hp_multiplier FROM profiles WHERE id=u)<>1 OR (SELECT next_order_free_delivery_cap FROM profiles WHERE id=u)<>0 OR (SELECT balance FROM wallets WHERE user_id=u)<>4800 THEN RAISE EXCEPTION 'legacy conversion/charge incorrect';END IF;
 -- New gifts arriving before a retry/cancellation belong to the customer too.
 UPDATE profiles SET next_order_hp_multiplier=3,next_order_free_delivery_cap=350 WHERE id=u;
 r:=pg_temp.legacy_checkout(u,c,meal,intent,line,100,200);
 IF (r->>'order_id')::uuid IS DISTINCT FROM oid OR (SELECT balance FROM wallets WHERE user_id=u)<>4800 OR (SELECT count(*) FROM exclusive_spin_fulfillments WHERE user_id=u)<>1 OR (SELECT next_order_hp_multiplier FROM profiles WHERE id=u)<>3 THEN RAISE EXCEPTION 'lost-response replay consumed a new gift';END IF;
 r:=hg_refund_order_atomic(oid,u,'legacy-cancel',NULL,'[AUDIT rollback] Cancel before preparation',true);
 IF NOT coalesce((r->>'success')::boolean,false) OR (SELECT balance FROM wallets WHERE user_id=u)<>5000 OR (SELECT next_order_free_delivery_cap FROM profiles WHERE id=u)<>350 OR (SELECT next_order_hp_multiplier FROM profiles WHERE id=u)<>3 OR NOT EXISTS(SELECT 1 FROM exclusive_spin_fulfillments WHERE id=converted AND status='pending' AND applied_order_id IS NULL AND (result_snapshot->'reward_config'->>'multiplier')::numeric=2) THEN RAISE EXCEPTION 'cancellation damaged new/old benefits: %',r;END IF;
 r:=hg_refund_order_atomic(oid,u,'legacy-cancel-retry',NULL,'[AUDIT rollback] Different retry intent',true);
 IF (SELECT balance FROM wallets WHERE user_id=u)<>5000 OR (SELECT next_order_free_delivery_cap FROM profiles WHERE id=u)<>350 OR (SELECT count(*) FROM exclusive_spin_fulfillments WHERE user_id=u)<>1 THEN RAISE EXCEPTION 'repeat cancellation duplicated restoration';END IF;
 changed:=jsonb_set(jsonb_set(line,'{_hp_bonus_plan,multiplier}','4'),'{_delivery_benefit}',jsonb_build_object('source','legacy_spin','cap',350,'original_fee',500,'discount',350));
 BEGIN
  r:=pg_temp.legacy_checkout(u,c,meal,gen_random_uuid()::text,changed,150,250);
  IF coalesce((r->>'success')::boolean,false) OR r->>'error' IS DISTINCT FROM 'hp_bonus_changed' THEN RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='changed legacy terms were not explicitly refused';END IF;
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'hp_bonus_changed' THEN RAISE;END IF;END;
 IF (SELECT balance FROM wallets WHERE user_id=u)<>5000 OR (SELECT next_order_hp_multiplier FROM profiles WHERE id=u)<>3 OR (SELECT next_order_free_delivery_cap FROM profiles WHERE id=u)<>350 THEN RAISE EXCEPTION 'rejected changed terms consumed money or gifts';END IF;
END$$;
ROLLBACK;
SELECT 'passed: atomic legacy delivery-cap/HP conversion, interruption, replay preserving newer gifts, cancellation/restoration/retry conservation and changed-term refusal; isolated fixtures rolled back' evidence;
