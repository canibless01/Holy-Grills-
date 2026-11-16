BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.ca_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Checkout abandonment: %',label;END IF;END$$;
CREATE FUNCTION pg_temp.ca_person(c uuid) RETURNS uuid LANGUAGE plpgsql AS $$DECLARE u uuid:=gen_random_uuid();BEGIN
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-ca-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Checkout release"}');
 UPDATE profiles SET campus_id=c,role='student' WHERE id=u;
 INSERT INTO wallets(user_id,balance,currency,campus_id) VALUES(u,1000,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=1000;
 RETURN u;
END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();u uuid;other_user uuid;k text;raw text;unknown_key text;oid uuid:=gen_random_uuid();paid uuid:=gen_random_uuid();guest uuid:=gen_random_uuid();r jsonb;initial numeric;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Checkout release','audit-ca-'||c);
 u:=pg_temp.ca_person(c);other_user:=pg_temp.ca_person(c);
 raw:=gen_random_uuid()::text;unknown_key:='v2:'||md5(raw)||md5(raw||'scoped');
 r:=hg_abandon_checkout(u,c,unknown_key,raw);
 PERFORM pg_temp.ca_check(r->>'state'='closed','unknown response can be closed without creating/paying an order');
 r:=hg_create_order_atomic(p_user_id=>u,p_guest_name=>NULL,p_guest_email=>NULL,p_guest_phone=>NULL,p_claim_token=>NULL,p_subtotal=>0,p_delivery_fee=>0,p_discount_amount=>0,p_total_amount=>0,p_delivery_type=>'on_campus',p_delivery_location_id=>NULL,p_delivery_location_lat=>NULL,p_delivery_location_lon=>NULL,p_delivery_address_snapshot=>'{}',p_delivery_window_id=>NULL,p_squad_name=>NULL,p_notes=>NULL,p_idempotency_key=>unknown_key,p_promo_code_id=>NULL,p_items=>'[]');
 PERFORM pg_temp.ca_check(r->>'error'='checkout_intent_closed','late creation cannot revive closed intent');
 PERFORM pg_temp.ca_check(NOT EXISTS(SELECT 1 FROM orders WHERE idempotency_key=unknown_key),'no unwanted order or wallet charge');
 raw:=gen_random_uuid()::text;k:='v2:'||md5(raw)||md5(raw||'scoped');
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,wallet_amount_used,card_amount_used,idempotency_key) VALUES(oid,u,c,'received','pending',500,500,200,300,k);
 UPDATE wallets SET balance=800 WHERE user_id=u;
 INSERT INTO wallet_transactions(user_id,type,amount,balance_after,reference_type,reference_id,provider,provider_reference,campus_id) VALUES(u,'debit',200,800,'order',oid,'internal','audit-ca-debit-'||oid,c);
 BEGIN
  PERFORM hg_abandon_checkout(other_user,c,k,raw);
  RAISE EXCEPTION 'Wrong owner unexpectedly accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 r:=hg_abandon_checkout(u,c,k,raw);
 PERFORM pg_temp.ca_check(r->>'state'='closed','unpaid split checkout released');
 PERFORM pg_temp.ca_check((SELECT balance=1000 FROM wallets WHERE user_id=u),'only collected wallet portion restored');
 PERFORM pg_temp.ca_check((SELECT status='cancelled' AND payment_status='failed' FROM orders WHERE id=oid),'unpaid order closed');
 PERFORM pg_temp.ca_check((SELECT coalesce(sum(amount),0)=200 FROM wallet_transactions WHERE reference_id=oid AND reference_type='refund' AND type='credit'),'no refund for unpaid card portion');
 r:=hg_abandon_checkout(u,c,k,raw);
 PERFORM pg_temp.ca_check((SELECT balance=1000 FROM wallets WHERE user_id=u),'lost-response retry cannot refund twice');
 raw:=gen_random_uuid()::text;k:='v2:'||md5(raw)||md5(raw||'scoped');
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,total_amount,card_amount_used,idempotency_key) VALUES(paid,u,c,'received','paid',500,500,k);
 r:=hg_abandon_checkout(u,c,k,raw);
 PERFORM pg_temp.ca_check(r->>'state'='paid' AND r->'order'->>'id'=paid::text,'paid result returns original order');
 PERFORM pg_temp.ca_check((SELECT payment_status='paid' AND status='received' FROM orders WHERE id=paid),'paid order never cancelled');
 PERFORM pg_temp.ca_check(NOT EXISTS(SELECT 1 FROM hg_internal.checkout_intent_closures WHERE intent_key=k),'paid intent not tombstoned');
 raw:=gen_random_uuid()::text;k:='v2:'||md5(raw)||md5(raw||'scoped');
 INSERT INTO orders(id,campus_id,guest_email,guest_phone,status,payment_status,total_amount,card_amount_used,idempotency_key) VALUES(guest,c,'guest@example.invalid','08012345678','received','pending',500,500,k);
 BEGIN
  PERFORM hg_abandon_checkout(NULL,c,k,raw,'wrong@example.invalid','08012345678');
  RAISE EXCEPTION 'Wrong guest unexpectedly accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 r:=hg_abandon_checkout(NULL,c,k,raw,'guest@example.invalid','08012345678');
 PERFORM pg_temp.ca_check(r->>'state'='closed' AND (SELECT payment_status='failed' AND status='cancelled' FROM orders WHERE id=guest),'guest unpaid cancellation requires matching proof');
 PERFORM pg_temp.ca_check(NOT has_function_privilege('authenticated','public.hg_abandon_checkout(uuid,uuid,text,text,text,text)','execute'),'service-only money mutation');
 RAISE NOTICE 'PASS: unknown-response closure, late-create prevention, owner/guest proof, wallet-only split restoration, replay conservation and paid-order protection';
END $test$;
ROLLBACK;
