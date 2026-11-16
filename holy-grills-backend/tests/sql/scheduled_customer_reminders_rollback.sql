BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();u uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();o uuid:=gen_random_uuid();guest_o uuid:=gen_random_uuid();unpaid uuid:=gen_random_uuid();later uuid:=gen_random_uuid();test_o uuid:=gen_random_uuid();today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;stamp timestamptz;r jsonb;claim jsonb;guest_notice uuid;member_notice uuid;began boolean;
BEGIN
 stamp:=today::timestamp AT TIME ZONE 'Africa/Lagos';
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Reminders','audit-reminder-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-reminder-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Reminder"}');
 UPDATE profiles SET campus_id=c,role='student',is_active=true,push_enabled=true,email_notifications=true WHERE id=u;
 INSERT INTO notification_preferences(user_id,order_updates,push_enabled,email_enabled) VALUES(u,true,true,true) ON CONFLICT(user_id) DO UPDATE SET order_updates=true,push_enabled=true,email_enabled=true;
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,is_scheduled,scheduled_for,is_test) VALUES(o,u,c,'received','paid',true,stamp,false),(unpaid,u,c,'received','pending',true,stamp,false),(later,u,c,'received','paid',true,stamp+interval '1 day',false);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(sa,'audit-reminder-'||sa||'@example.invalid','{"full_name":"[AUDIT rollback] Reminder test admin"}');
 UPDATE profiles SET role='super_admin',campus_id=c WHERE id=sa;
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,is_scheduled,scheduled_for) VALUES(test_o,sa,c,'received','paid',true,stamp);
 INSERT INTO orders(id,campus_id,status,payment_status,is_scheduled,scheduled_for,guest_email,guest_name,claim_token) VALUES(guest_o,c,'received','paid',true,stamp,'audit-guest@example.invalid','Guest',gen_random_uuid());
 BEGIN PERFORM hg_queue_scheduled_order_reminders(0,c);RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='simulate interruption';EXCEPTION WHEN no_data_found THEN NULL;END;
 IF EXISTS(SELECT 1 FROM notification_deliveries WHERE campus_id=c) THEN RAISE EXCEPTION 'aborted scan retained messages';END IF;
 r:=hg_queue_scheduled_order_reminders(0,c);
 IF (r->>'orders')::integer<>2 OR jsonb_array_length(r->'notification_ids')<>3 THEN RAISE EXCEPTION 'wrong due/paid/test scope: %',r;END IF;
 r:=hg_queue_scheduled_order_reminders(0,c);
 IF (r->>'orders')::integer<>0 OR (SELECT count(*) FROM notifications WHERE user_id=u AND type='scheduled_order_reminder')<>3 OR (SELECT count(*) FROM notification_deliveries WHERE campus_id=c)<>3 THEN RAISE EXCEPTION 'repeated scan duplicated channels';END IF;
 SELECT id INTO guest_notice FROM notification_deliveries WHERE campus_id=c AND user_id IS NULL;
 claim:=hg_claim_notification_dispatch_v2(guest_notice);
 IF claim->>'state'<>'claimed' OR claim->'payload'->'notification'->'metadata'->>'order_id'<>guest_o::text THEN RAISE EXCEPTION 'guest receipt not recoverable';END IF;
 IF NOT hg_begin_notification_dispatch(guest_notice,(claim->>'token')::uuid,'{}') THEN RAISE EXCEPTION 'valid guest cannot send';END IF;
 -- Rescheduling after generation invalidates the notice at the final boundary.
 SELECT id INTO member_notice FROM notification_deliveries WHERE campus_id=c AND user_id=u AND channel='push';
 claim:=hg_claim_notification_dispatch_v2(member_notice);
 UPDATE orders SET scheduled_for=stamp+interval '1 day' WHERE id=o;
 began:=hg_begin_notification_dispatch(member_notice,(claim->>'token')::uuid,'{}');
 IF began OR (SELECT status FROM notification_deliveries WHERE id=member_notice)<>'cancelled' THEN RAISE EXCEPTION 'rescheduled order reached provider';END IF;
 IF hg_scheduled_order_reminder_valid(guest_o,u,today,'audit-guest@example.invalid') OR hg_scheduled_order_reminder_valid(guest_o,NULL,today,'wrong@example.invalid') THEN RAISE EXCEPTION 'owner/email mismatch allowed';END IF;
 UPDATE orders SET status='cancelled' WHERE id=guest_o;
 IF hg_scheduled_order_reminder_valid(guest_o,NULL,today,'audit-guest@example.invalid') THEN RAISE EXCEPTION 'cancelled guest still eligible';END IF;
 IF has_function_privilege('authenticated','public.hg_queue_scheduled_order_reminders(integer,uuid)','execute') OR has_function_privilege('anon','public.hg_scheduled_order_reminder_valid(uuid,uuid,date,text)','execute') THEN RAISE EXCEPTION 'reminder functions public';END IF;
END$$;
ROLLBACK;
SELECT 'passed: paid member/guest capture, interruption rollback, idempotence, future/unpaid/test exclusions, guest recovery, reschedule/cancellation/ownership/send-boundary guards; fixtures rolled back' evidence;
