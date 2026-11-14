BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.gc_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Guest recovery: %',label;END IF;END$$;
CREATE FUNCTION pg_temp.gc_cart(c uuid,email text,age interval DEFAULT interval '35 minutes') RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE oid uuid:=gen_random_uuid();cid uuid:=gen_random_uuid();
BEGIN
 INSERT INTO orders(id,campus_id,guest_name,guest_email,guest_phone,claim_token,status,payment_status,total_amount,card_amount_used,created_at)
 VALUES(oid,c,'[AUDIT rollback] Guest',email,'08012345678',gen_random_uuid(),'received','pending',100,100,now()-age);
 INSERT INTO abandoned_carts(id,campus_id,guest_email,guest_phone,last_active_at,cart_payload)
 VALUES(cid,c,email,'08012345678',now()-age,jsonb_build_object('pending_order_id',oid));
 RETURN cid;
END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();cid uuid;oid uuid;notice uuid;lease uuid;other uuid;other_order uuid;
 email text:='audit-guest-'||gen_random_uuid()||'@example.invalid';r jsonb;m jsonb;due jsonb;ends_at timestamptz:=now()+interval '1 hour';
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Guest recovery','audit-gc-'||c);
 INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES('abandoned_cart_nudge',true,c);
 INSERT INTO system_settings(key,value,campus_id,is_public) VALUES('campus_cart_recovery','{"initial_minutes":30,"repeat_minutes":1440,"max_hours":48}',c,false);
 cid:=pg_temp.gc_cart(c,email);SELECT (cart_payload->>'pending_order_id')::uuid INTO oid FROM abandoned_carts WHERE id=cid;
 due:=hg_due_guest_cart_recovery(c);
 PERFORM pg_temp.gc_check(jsonb_array_length(due)=1 AND due->0->>'id'=cid::text,'eligible guest is discovered');
 r:=hg_capture_guest_cart_recovery_step(cid,0,ends_at);
 PERFORM pg_temp.gc_check((r->>'saved')::boolean,'guest email captured');notice:=(r->'notification_ids'->>0)::uuid;
 PERFORM pg_temp.gc_check((SELECT user_id IS NULL AND channel='email' AND status='queued' FROM notification_deliveries WHERE id=notice),'email has no synthetic account or push');
 PERFORM pg_temp.gc_check(NOT EXISTS(SELECT 1 FROM notifications WHERE id=notice),'no fake in-app notification');
 m:=hg_cart_recovery_metrics(ARRAY[cid])->cid::text;
 PERFORM pg_temp.gc_check((m->>'saved_nudges')::integer=1 AND (m->>'email_accepted')::integer=0 AND (m->>'delivery_pending')::integer=1,'queued is not reported as sent');
 r:=hg_capture_guest_cart_recovery_step(cid,0,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'capture replay is deduplicated');
 r:=hg_claim_notification_dispatch_v2(notice);lease:=(r->>'token')::uuid;
 PERFORM pg_temp.gc_check(r->>'state'='claimed','existing dispatcher claims email');
 PERFORM pg_temp.gc_check(hg_claim_notification_dispatch_v2(notice)->>'state'='busy','second worker cannot send');
 PERFORM pg_temp.gc_check(hg_begin_guest_cart_dispatch(notice,lease,'{"test":"prepared"}'),'send-time eligibility checked');
 PERFORM pg_temp.gc_check(hg_finish_notification_dispatch(notice,lease,'{"state":"accepted","provider":"test"}'),'receipt saved without real transport');
 m:=hg_cart_recovery_metrics(ARRAY[cid])->cid::text;
 PERFORM pg_temp.gc_check((m->>'email_accepted')::integer=1 AND (m->>'delivery_pending')::integer=0,'accepted receipt appears in operator counters');
 other:=pg_temp.gc_cart(c,email,interval '34 minutes');
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);
 PERFORM pg_temp.gc_check(r->>'reason'='recipient_throttled','new checkouts cannot spam the same email');
 PERFORM pg_temp.gc_check(NOT hg_guest_cart_recovery_valid(cid,0,ends_at,email,oid),'newer checkout supersedes old reminder');
 -- Payment after capture but before dispatch must stop the email.
 other:=pg_temp.gc_cart(c,'paid-'||email);SELECT (cart_payload->>'pending_order_id')::uuid INTO other_order FROM abandoned_carts WHERE id=other;
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);notice:=(r->'notification_ids'->>0)::uuid;
 r:=hg_claim_notification_dispatch_v2(notice);lease:=(r->>'token')::uuid;
 UPDATE orders SET payment_status='paid' WHERE id=other_order;
 PERFORM pg_temp.gc_check(NOT hg_begin_guest_cart_dispatch(notice,lease,'{}'),'paid checkout blocked at handoff');
 PERFORM pg_temp.gc_check((SELECT status='cancelled' FROM notification_deliveries WHERE id=notice),'stale email cancelled');
 -- Explicit opt-out is idempotent and is rechecked even after a worker claims.
 other:=pg_temp.gc_cart(c,'optout-'||email);r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);notice:=(r->'notification_ids'->>0)::uuid;
 r:=hg_claim_notification_dispatch_v2(notice);lease:=(r->>'token')::uuid;
 PERFORM pg_temp.gc_check(hg_unsubscribe_guest_cart_email(notice) AND hg_unsubscribe_guest_cart_email(notice),'unsubscribe replay safe');
 PERFORM pg_temp.gc_check(NOT hg_begin_guest_cart_dispatch(notice,lease,'{}'),'opt-out before handoff prevents send');
 -- No immediate reminder, no preparation-window overrun, no cancelled checkout.
 other:=pg_temp.gc_cart(c,'recent-'||email,interval '5 minutes');
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'thirty-minute inactivity enforced');
 other:=pg_temp.gc_cart(c,'cutoff-'||email);
 r:=hg_capture_guest_cart_recovery_step(other,0,now());PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'preparation cutoff stops capture');
 SELECT (cart_payload->>'pending_order_id')::uuid INTO other_order FROM abandoned_carts WHERE id=other;
 UPDATE orders SET status='cancelled',payment_status='failed' WHERE id=other_order;
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'cancelled checkout suppressed');
 -- Mismatched ownership/contact cannot expose another private checkout.
 other:=pg_temp.gc_cart(c,'wrong-'||email);SELECT (cart_payload->>'pending_order_id')::uuid INTO other_order FROM abandoned_carts WHERE id=other;
 PERFORM pg_temp.gc_check(NOT hg_guest_cart_recovery_valid(other,0,ends_at,'wrong-address@example.invalid',other_order),'recipient must match persisted guest');
 UPDATE abandoned_carts SET guest_phone='08099999999' WHERE id=other;
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'contact proof must match order');
 other:=pg_temp.gc_cart(c,'repeat-'||email,interval '25 hours');
 r:=hg_capture_guest_cart_recovery_step(other,0,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'missed initial step is not replayed in a burst');
 r:=hg_capture_guest_cart_recovery_step(other,1,ends_at);PERFORM pg_temp.gc_check((r->>'saved')::boolean,'current daily reminder step can be captured');
 UPDATE abandoned_carts SET last_active_at=now()-interval '49 hours' WHERE id=other;
 r:=hg_capture_guest_cart_recovery_step(other,2,ends_at);PERFORM pg_temp.gc_check(NOT (r->>'saved')::boolean,'reminders stop after forty-eight hours');
 PERFORM pg_temp.gc_check(NOT has_function_privilege('anon','public.hg_unsubscribe_guest_cart_email(uuid)','execute') AND NOT has_function_privilege('authenticated','public.hg_capture_guest_cart_recovery_step(uuid,integer,timestamptz,integer,integer,integer)','execute'),'browser cannot queue or suppress arbitrary recipients');
 PERFORM pg_temp.gc_check(NOT has_table_privilege('anon','hg_internal.guest_cart_email_optouts','select'),'private preferences are not exposed');
END $test$;
ROLLBACK;
SELECT 'passed: guest capture/replay, worker lease, payment race, unsubscribe, cutoff, contact proof, throttling, counters and service-only access; all fixtures rolled back' AS evidence;
