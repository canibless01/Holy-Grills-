BEGIN;
DO $$
DECLARE c uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); actor uuid:=gen_random_uuid(); amb uuid:=gen_random_uuid(); amb2 uuid:=gen_random_uuid(); customer uuid:=gen_random_uuid(); foreign_amb uuid:=gen_random_uuid(); oid uuid; mid uuid:=gen_random_uuid();r jsonb; self_result jsonb;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'Local metrics','local-'||c),(c2,'Foreign metrics','local-'||c2);
 INSERT INTO auth.users(id,email) SELECT id,id||'@example.invalid' FROM unnest(ARRAY[actor,amb,amb2,customer,foreign_amb]) id;
 INSERT INTO profiles(id,email,role,campus_id,full_name,is_active,created_at,hp_balance)
 SELECT id,id||'@example.invalid',CASE WHEN id=actor THEN 'community_manager' ELSE 'student' END::user_role,CASE WHEN id=foreign_amb THEN c2 ELSE c END,'Local metrics user',true,'2026-11-24 10:00Z',CASE WHEN id=customer THEN 50 ELSE 0 END FROM unnest(ARRAY[actor,amb,amb2,customer,foreign_amb]) id ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,created_at=excluded.created_at,hp_balance=excluded.hp_balance;
 INSERT INTO ambassadors(profile_id,campus_id,status) VALUES(amb,c,'active'),(amb2,c,'active'),(foreign_amb,c2,'active');
 INSERT INTO ambassador_link_clicks(ref_code,ambassador_id,visitor_user_id,campus_id,created_at) VALUES('A',amb,customer,c,'2026-11-24 09:00Z'),('A',amb,customer,c,'2026-11-24 09:10Z'),('B',amb2,customer,c,'2026-11-24 09:20Z');
 FOR i IN 1..4 LOOP
  oid:=gen_random_uuid();
  INSERT INTO orders(id,user_id,campus_id,subtotal,delivery_fee,total_amount,status,payment_status,delivered_at,card_refund_total,is_test)
   VALUES(oid,customer,c,2000,500,2500,'delivered',CASE WHEN i=2 THEN 'partially_refunded'::payment_status WHEN i=3 THEN 'refunded'::payment_status ELSE 'paid'::payment_status END,'2026-11-24 20:00Z',CASE WHEN i=2 THEN 1000 WHEN i=3 THEN 2500 ELSE 0 END,i=4);
  INSERT INTO ambassador_order_attributions(order_id,customer_user_id,ambassador_id,campus_id,order_total,eligibility) VALUES(oid,customer,amb,c,2500,'eligible');
 END LOOP;
 INSERT INTO ambassador_promo_messages(id,created_by,campus_id,caption,month) VALUES(mid,actor,c,'Hello {{link}}','2026-11');
 INSERT INTO ambassador_promo_assignments(message_id,ambassador_id,month,status,created_at) VALUES(mid,amb,'2026-11','shared','2026-11-24 09:00Z');
 INSERT INTO system_settings(key,value,campus_id) VALUES('ambassador_expected_weekly_shares','3',c);
 r:=hg_ambassador_insights(actor,c,'2026-11','2026-11-23',amb);
 IF jsonb_array_length(r->'ambassadors')<>1 OR (r->'ambassadors'->0->'lifetime'->>'total_signups')::int<>1 OR (r->'ambassadors'->0->'lifetime'->>'total_orders')::int<>2 OR (r->'ambassadors'->0->'lifetime'->>'total_order_value')::numeric<>4000 THEN RAISE EXCEPTION 'verified signup/order totals: %',r; END IF;
 IF (r->'ambassadors'->0->'month'->>'monthly_share_target')::int<>12 THEN RAISE EXCEPTION 'campus target ignored'; END IF;
 IF (r->'ambassadors'->0->'week'->>'orders')::int<>2 OR (r->'ambassadors'->0->'week'->>'shared_count')::int<>1 THEN RAISE EXCEPTION 'weekly totals'; END IF;
 r:=hg_ambassador_insights(actor,c,'2026-11','2026-11-23',amb2);
 IF (r->'ambassadors'->0->'lifetime'->>'total_signups')::int<>0 THEN RAISE EXCEPTION 'signup double attributed'; END IF;
 self_result:=hg_ambassador_insights(amb,c,'2026-11','2026-11-23',foreign_amb);
 IF self_result->>'error'<>'forbidden' THEN RAISE EXCEPTION 'ambassador read another person'; END IF;
 r:=hg_ambassador_insights(actor,c2,'2026-11','2026-11-23');
 IF r->>'error'<>'forbidden' THEN RAISE EXCEPTION 'foreign campus read'; END IF;
 INSERT INTO hp_transactions(user_id,type,amount,balance_after,remaining_amount,source,status,campus_id) VALUES(customer,'earn',50,50,50,'welcome','active',c),(customer,'earn',20,50,null,'review','pending',c);
 UPDATE profiles SET role='admin' WHERE id=actor;
 r:=hg_hp_reconciliation(actor,c,'2026-11-01','2026-12-01');
 IF (r->>'profile_active_balance')::int<>50 OR (r->>'ledger_active_remaining')::int<>50 OR (r->>'pending_amount')::int<>20 OR (r->>'active_balance_difference')::int<>0 THEN RAISE EXCEPTION 'active/pending reconciliation: %',r; END IF;
 UPDATE profiles SET hp_balance=55 WHERE id=customer;
 r:=hg_hp_reconciliation(actor,c,'2026-11-01','2026-12-01');
 IF (r->>'active_balance_difference')::int<>5 THEN RAISE EXCEPTION 'mismatch hidden'; END IF;
 UPDATE ambassador_promo_messages SET deleted_at=now() WHERE id=mid;
 r:=hg_ambassador_insights(actor,c,'2026-11','2026-11-23',amb);
 IF (r->'ambassadors'->0->'week'->>'shared_count')::int<>0 THEN RAISE EXCEPTION 'deleted promo counted'; END IF;
 IF has_function_privilege('authenticated','hg_ambassador_insights(uuid,uuid,text,date,uuid)','EXECUTE') OR has_function_privilege('anon','hg_hp_reconciliation(uuid,uuid,timestamptz,timestamptz)','EXECUTE') THEN RAISE EXCEPTION 'public report privilege'; END IF;
END $$;
ROLLBACK;
SELECT 'verified first signup, delivered/refunded/test orders, week, scope and HP reconciliation passed; rolled back' AS evidence;
