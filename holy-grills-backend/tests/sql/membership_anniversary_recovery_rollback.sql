BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.ma_assert(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Membership: %',label;END IF;END$$;
DO $$
DECLARE c uuid:=gen_random_uuid();u uuid:=gen_random_uuid();legacy_u uuid:=gen_random_uuid();actor uuid;milestone integer;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;r jsonb;ref uuid;v_month text:=to_char(today,'YYYY-MM');
BEGIN
 SELECT coalesce(max(months),0)+120 INTO milestone FROM membership_rewards;
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Membership','audit-membership-'||c);
 FOREACH actor IN ARRAY ARRAY[u,legacy_u] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-membership-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Membership"}');
  UPDATE profiles SET campus_id=c,role='student',is_active=true,hp_balance=0,push_enabled=true,created_at=(today-make_interval(months=>milestone))::date::timestamp AT TIME ZONE 'Africa/Lagos' WHERE id=actor;
 END LOOP;
 INSERT INTO membership_rewards(months,hp_awarded,is_active,campus_id) VALUES(milestone,70,true,c);
 BEGIN
  r:=hg_award_membership_anniversary(u);RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='simulate process interruption';
 EXCEPTION WHEN no_data_found THEN NULL;END;
 PERFORM pg_temp.ma_assert((SELECT hp_balance=0 FROM profiles WHERE id=u) AND NOT EXISTS(SELECT 1 FROM notifications WHERE user_id=u) AND NOT EXISTS(SELECT 1 FROM hp_transactions WHERE user_id=u),'all effects roll back');
 r:=hg_award_membership_anniversary(u);ref:=(r->>'reference_id')::uuid;
 PERFORM pg_temp.ma_assert((r->>'awarded')::integer=70,'configured initial grant');
 UPDATE membership_rewards SET hp_awarded=999 WHERE campus_id=c;
 r:=hg_award_membership_anniversary(u);
 PERFORM pg_temp.ma_assert((r->>'replayed')::boolean AND (r->>'awarded')::integer=0 AND (r->>'hp')::integer=70,'changed config preserves original terms');
 PERFORM pg_temp.ma_assert((SELECT hp_balance=70 FROM profiles WHERE id=u) AND (SELECT total_earned=70 FROM monthly_hp_tracker WHERE user_id=u AND month=v_month),'balance and monthly counted once');
 PERFORM pg_temp.ma_assert((SELECT count(*)=2 FROM notifications WHERE reference_id=ref) AND (SELECT count(*)=1 FROM notification_deliveries WHERE user_id=u),'one inbox/push receipt');
 -- Adopt an old grant whose NULL reference used to make retries unsafe.
 r:=record_hp_transaction_atomic(legacy_u,25,'earn','active','membership_anniversary','membership_anniversary',NULL,NULL,'Membership anniversary — '||milestone||' months',c);
 INSERT INTO notifications(user_id,type,title,body,channel,campus_id) VALUES(legacy_u,'membership_anniversary','Existing notice','Already notified','in_app',c);
 r:=hg_award_membership_anniversary(legacy_u);
 PERFORM pg_temp.ma_assert((r->>'hp')::integer=25 AND (r->>'awarded')::integer=0 AND (SELECT hp_balance=25 FROM profiles WHERE id=legacy_u),'legacy original grant adopted');
 PERFORM pg_temp.ma_assert((SELECT count(*)=1 FROM notifications WHERE user_id=legacy_u AND channel='in_app'),'old random-id inbox preserved');
 r:=hg_award_membership_anniversary(legacy_u);
 PERFORM pg_temp.ma_assert((SELECT count(*)=2 FROM notifications WHERE user_id=legacy_u),'missing legacy push captured once');
 UPDATE profiles SET is_active=false WHERE id=u;r:=hg_award_membership_anniversary(u);
 PERFORM pg_temp.ma_assert(r->>'reason'='excluded','inactive excluded');
 UPDATE profiles SET is_active=true,role='super_admin' WHERE id=u;r:=hg_award_membership_anniversary(u);
 PERFORM pg_temp.ma_assert(r->>'reason'='excluded','nonstudent excluded');
 PERFORM pg_temp.ma_assert(('2026-01-31'::date+interval '3 months')::date='2026-04-30'::date,'month-end calendar clamp');
 PERFORM pg_temp.ma_assert(NOT has_function_privilege('authenticated','public.hg_award_membership_anniversary(uuid)','execute') AND NOT has_function_privilege('anon','public.hg_award_membership_anniversary(uuid)','execute'),'backend-only execution');
END$$;
ROLLBACK;
SELECT 'passed: atomic grant/monthly/notices, interruption, replay after config change, legacy receipt/channel adoption, active student guard, calendar clamp and permissions; fixtures rolled back' evidence;
