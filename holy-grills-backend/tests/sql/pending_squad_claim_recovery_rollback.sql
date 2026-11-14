BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.sc_assert(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Squad claim: %',label;END IF;END$$;
DO $$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();u uuid:=gen_random_uuid();owner_id uuid:=gen_random_uuid();o uuid:=gen_random_uuid();p uuid:=gen_random_uuid();o2 uuid:=gen_random_uuid();p2 uuid:=gen_random_uuid();o3 uuid:=gen_random_uuid();p3 uuid:=gen_random_uuid();o4 uuid:=gen_random_uuid();p4 uuid:=gen_random_uuid();actor uuid;r jsonb;email text;v_month text:=to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM');sid uuid:=gen_random_uuid();other_sid uuid:=gen_random_uuid();
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Squad claim','audit-squad-claim-'||c),(other_c,'[AUDIT rollback] Other','audit-squad-claim-'||other_c);
 FOREACH actor IN ARRAY ARRAY[u,owner_id] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-squad-claim-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Squad claim"}');
  UPDATE profiles SET campus_id=c,role='student',hp_balance=0,push_enabled=true WHERE id=actor;
 END LOOP;
 SELECT profiles.email::text INTO email FROM profiles WHERE id=u;
 INSERT INTO notification_preferences(user_id,hp_updates,push_enabled) VALUES(u,true,true) ON CONFLICT(user_id) DO UPDATE SET hp_updates=true,push_enabled=true;
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,is_squad_order,squad_hp_distributed) VALUES(o,owner_id,c,'delivered','paid',true,true),(o2,owner_id,c,'delivered','paid',true,true),(o3,owner_id,c,'delivered','paid',true,true);
 INSERT INTO pending_squad_hp(id,email,order_id,campus_id,hp_amount,status) VALUES(p,email,o,c,25,'pending'),(p2,email,o2,c,17,'pending'),(p3,email,o3,c,11,'pending');
 UPDATE profiles SET campus_id=other_c WHERE id=u;
 r:=hg_claim_pending_squad_hp(p,u);PERFORM pg_temp.sc_assert(r->>'error'='squad_recipient_unavailable','cross-campus denied');
 UPDATE profiles SET campus_id=c,is_active=false WHERE id=u;
 r:=hg_claim_pending_squad_hp(p,u);PERFORM pg_temp.sc_assert(r->>'error'='squad_recipient_unavailable','inactive denied');
 UPDATE profiles SET is_active=true WHERE id=u;
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,is_squad_order,squad_hp_distributed) VALUES(o4,owner_id,c,'received','pending',true,true);
 INSERT INTO pending_squad_hp(id,email,order_id,campus_id,hp_amount,status) VALUES(p4,email,o4,c,9,'pending');
 r:=hg_claim_pending_squad_hp(p4,u);PERFORM pg_temp.sc_assert(r->>'error'='delivered_squad_share_required','unpaid unfulfilled order denied');
 -- An exception after the grant must roll back balance, monthly, marker and notices together.
 BEGIN
  r:=hg_claim_pending_squad_hp(p,u);
  RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='simulated caller abort';
 EXCEPTION WHEN no_data_found THEN NULL;END;
 PERFORM pg_temp.sc_assert((SELECT hp_balance=0 FROM profiles WHERE id=u) AND (SELECT status='pending' FROM pending_squad_hp WHERE id=p) AND NOT EXISTS(SELECT 1 FROM notifications WHERE reference_id=o),'interrupted transaction leaves no effects');
 r:=hg_claim_pending_squad_hp(p,u);PERFORM pg_temp.sc_assert((r->>'awarded')::integer=25,'first claim');
 r:=hg_claim_pending_squad_hp(p,u);PERFORM pg_temp.sc_assert((r->>'replayed')::boolean,'response-loss replay');
 PERFORM pg_temp.sc_assert((SELECT hp_balance=25 FROM profiles WHERE id=u) AND (SELECT total_earned=25 FROM monthly_hp_tracker WHERE user_id=u AND monthly_hp_tracker.month=v_month),'one balance and monthly increment');
 PERFORM pg_temp.sc_assert((SELECT count(*)=2 FROM notifications WHERE user_id=u AND reference_id=o) AND (SELECT count(*)=1 FROM notification_deliveries WHERE user_id=u AND notification_id IN (SELECT id FROM notifications WHERE reference_id=o)),'durable inbox and push exactly once');
 -- Adopt a pre-existing delivery share under its other reference key, never pay twice.
 r:=record_hp_transaction_atomic(u,17,'earn','active','squad_split','squad_split',o2,NULL,'[AUDIT rollback] existing delivery share',c);
 r:=hg_claim_pending_squad_hp(p2,u);PERFORM pg_temp.sc_assert((r->>'awarded')::integer=0 AND (SELECT hp_balance=42 FROM profiles WHERE id=u),'alternate receipt adopted without double award');
 r:=record_hp_transaction_atomic(u,99,'earn','active','squad_split_claimed','squad_split_claimed',o3,NULL,'[AUDIT rollback] mismatch',c);
 r:=hg_claim_pending_squad_hp(p3,u);PERFORM pg_temp.sc_assert(r->>'error'='legacy_squad_share_review_required' AND (SELECT status='pending' FROM pending_squad_hp WHERE id=p3),'mismatched legacy receipt held for review');
 INSERT INTO squads(id,name,creator_id,campus_id) VALUES(sid,'[AUDIT rollback] Squad',owner_id,c),(other_sid,'[AUDIT rollback] Other squad',owner_id,other_c);
 INSERT INTO squad_roster(squad_id,email) VALUES(sid,email),(other_sid,email);
 INSERT INTO squad_members(order_id,email,campus_id) VALUES(o,email,c),(o2,email,other_c);
 PERFORM hg_bind_squad_identity(u);
 PERFORM pg_temp.sc_assert((SELECT user_id=u FROM squad_roster WHERE squad_id=sid) AND (SELECT user_id IS NULL FROM squad_roster WHERE squad_id=other_sid),'roster binding campus scoped');
 PERFORM pg_temp.sc_assert((SELECT user_id=u FROM squad_members WHERE order_id=o) AND (SELECT user_id IS NULL FROM squad_members WHERE order_id=o2),'member binding checks row and order campus');
 UPDATE notification_preferences SET hp_updates=false WHERE user_id=u;
 DELETE FROM hp_transactions WHERE user_id=u AND reference_id=o3;UPDATE profiles SET hp_balance=42 WHERE id=u;
 r:=hg_claim_pending_squad_hp(p3,u);PERFORM pg_temp.sc_assert((r->>'awarded')::integer=11 AND NOT EXISTS(SELECT 1 FROM notifications WHERE reference_id=o3),'HP opt-out suppresses notices without suppressing award');
 PERFORM pg_temp.sc_assert(NOT has_function_privilege('anon','public.hg_claim_pending_squad_hp(uuid,uuid)','execute') AND NOT has_function_privilege('authenticated','public.hg_claim_pending_squad_hp(uuid,uuid)','execute') AND NOT has_function_privilege('authenticated','public.hg_bind_squad_identity(uuid)','execute'),'backend-only functions');
END$$;
ROLLBACK;
SELECT 'passed: atomic grant/monthly/marker/notice, rollback and replay, alternative-key adoption, mismatch review, campus/email/activity/payment guards, scoped invitations, preferences and backend-only permissions; fixtures rolled back' evidence;
