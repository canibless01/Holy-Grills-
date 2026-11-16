BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.cl_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Cushion ledger: %',label;END IF;END$$;
CREATE FUNCTION pg_temp.cl_order(c uuid,meal uuid,location uuid,total numeric DEFAULT 4000) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE o uuid:=gen_random_uuid();
BEGIN
 INSERT INTO orders(id,campus_id,guest_email,claim_token,status,payment_status,subtotal,delivery_fee,discount_amount,total_amount,card_amount_used,delivery_location_id)
 VALUES(o,c,'audit-ledger-'||o||'@example.invalid',gen_random_uuid(),'received','paid',3500,500,4000-total,total,total,location);
 INSERT INTO order_items(order_id,menu_item_id,campus_id,name_snapshot,price_snapshot,line_total,quantity)
 VALUES(o,meal,c,'[AUDIT rollback] Meal',3500,3500,1);
 RETURN o;
END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();cat uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();gate uuid:=gen_random_uuid();hostel uuid:=gen_random_uuid();o uuid;failed uuid;discounted uuid;kitchen uuid:=gen_random_uuid();n integer;l hg_internal.delivery_subsidy_ledger%rowtype;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Ledger','audit-ledger-'||c);
 INSERT INTO gates(id,name,campus_id) VALUES(gate,'[AUDIT rollback] Gate',c);
 INSERT INTO hostels(id,name,campus_id,gate_id,delivery_fee) VALUES(hostel,'[AUDIT rollback] Hostel',c,gate,500);
 INSERT INTO menu_categories(id,name,slug,campus_id) VALUES(cat,'[AUDIT rollback] Ledger','audit-ledger-'||cat,c);
 INSERT INTO menu_items(id,category_id,name,slug,price,cushion_amount,campus_id) VALUES(meal,cat,'[AUDIT rollback] Meal','audit-ledger-'||meal,3500,500,c);
 o:=pg_temp.cl_order(c,meal,gate);
 PERFORM pg_temp.cl_check(NOT EXISTS(SELECT 1 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'capture is deferred until order lines exist');
 SET CONSTRAINTS sync_delivery_subsidy IMMEDIATE;
 SELECT * INTO l FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o;
 PERFORM pg_temp.cl_check(l.cushion_original=500 AND l.delivery_fee_original=500 AND l.gate_id=gate,'paid admission captures complete lines and final delivery fee');
 PERFORM pg_temp.cl_check(l.cushion_total=0 AND l.net_effect IS NULL,'undelivered/unreconciled is not claimed as pool profit');
 -- Authenticated kitchen transitions still work while accounting stays private.
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(kitchen,'audit-ledger-'||kitchen||'@example.invalid','{"full_name":"[AUDIT rollback] Kitchen"}');
 UPDATE profiles SET campus_id=c,role='kitchen' WHERE id=kitchen;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',kitchen)::text,true);
 PERFORM set_config('role','authenticated',true);
 UPDATE orders SET status='preparing' WHERE id=o;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 PERFORM pg_temp.cl_check((SELECT status='preparing' FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'private accounting trigger supports authorized kitchen JWT');
 UPDATE orders SET status='ready' WHERE id=o;
 UPDATE orders SET status='out_for_delivery' WHERE id=o;
 UPDATE orders SET status='delivered',delivered_at=now() WHERE id=o;
 SELECT * INTO l FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o;
 PERFORM pg_temp.cl_check(l.cushion_total=500 AND l.delivery_fee_collected=500 AND l.net_effect IS NULL,'delivered income stays distinct from unknown rider cost');
 UPDATE hg_internal.delivery_subsidy_ledger SET rider_cost=900,rider_cost_date=(now() AT TIME ZONE 'Africa/Lagos')::date WHERE order_id=o;
 PERFORM pg_temp.cl_check((SELECT net_effect=100 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'500 cushion plus 500 customer delivery minus 900 rider leaves 100');
 UPDATE menu_items SET price=3900,cushion_amount=700 WHERE id=meal;
 PERFORM hg_internal.refresh_delivery_subsidy(o);
 PERFORM pg_temp.cl_check((SELECT cushion_original=500 AND net_effect=100 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'catalogue edits cannot rewrite ledger originals');
 UPDATE orders SET payment_status='partially_refunded',card_refund_total=1000 WHERE id=o;
 PERFORM pg_temp.cl_check((SELECT cushion_total=375 AND delivery_fee_collected=375 AND rider_cost=900 AND net_effect=-150 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'partial refund reverses proportionate collections but not rider expense');
 UPDATE orders SET status='refunded',payment_status='refunded',card_refund_total=4000 WHERE id=o;
 PERFORM pg_temp.cl_check((SELECT cushion_total=0 AND delivery_fee_collected=0 AND rider_cost=900 AND net_effect=-900 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=o),'full refund retains actual rider cost and reverses contributions');
 SELECT count(*) INTO n FROM hg_internal.delivery_subsidy_movements WHERE order_id=o;
 PERFORM hg_internal.refresh_delivery_subsidy(o);
 PERFORM pg_temp.cl_check((SELECT count(*) FROM hg_internal.delivery_subsidy_movements WHERE order_id=o)=n,'status replay does not repeat a reversal');
 SET CONSTRAINTS sync_delivery_subsidy DEFERRED;
 UPDATE menu_items SET price=3500,cushion_amount=500 WHERE id=meal;
 failed:=pg_temp.cl_order(c,meal,hostel);
 discounted:=pg_temp.cl_order(c,meal,gate,3500);
 SET CONSTRAINTS sync_delivery_subsidy IMMEDIATE;
 PERFORM pg_temp.cl_check((SELECT gate_id=gate FROM hg_internal.delivery_subsidy_ledger WHERE order_id=failed),'hostel uses its tagged gate');
 PERFORM pg_temp.cl_check((SELECT cushion_original=428.57 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=discounted),'food discount reduces actual cushion collected');
 UPDATE orders SET status='preparing' WHERE id=failed;
 UPDATE orders SET status='ready' WHERE id=failed;
 UPDATE orders SET status='out_for_delivery' WHERE id=failed;
 UPDATE orders SET status='delivery_attempted',delivery_attempted_at=now() WHERE id=failed;
 UPDATE hg_internal.delivery_subsidy_ledger SET rider_cost=300 WHERE order_id=failed;
 PERFORM pg_temp.cl_check((SELECT cushion_total=0 AND delivery_fee_collected=0 AND net_effect=-300 FROM hg_internal.delivery_subsidy_ledger WHERE order_id=failed),'failed delivery expense counts without pretending it was delivered');
 PERFORM pg_temp.cl_check((SELECT coalesce(sum(delta),0) FROM hg_internal.delivery_subsidy_movements WHERE campus_id=c)=(SELECT coalesce(sum(net_effect),0) FROM hg_internal.delivery_subsidy_ledger WHERE campus_id=c),'movement history conserves the current pool balance');
 PERFORM pg_temp.cl_check(NOT has_table_privilege('authenticated','hg_internal.delivery_subsidy_ledger','SELECT') AND NOT has_function_privilege('authenticated','hg_internal.refresh_delivery_subsidy(uuid)','execute'),'students cannot read or rewrite the ledger');
END $test$;
ROLLBACK;
SELECT 'passed: deferred paid capture, kitchen transition, delivered income, unknown costs, discounts, partial/full refund reversals, retained failed-delivery expenses, gate mapping and movement conservation; fixtures rolled back' AS evidence;
