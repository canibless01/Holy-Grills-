BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.er_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Evening reporting: %',label;END IF;END$$;
CREATE FUNCTION pg_temp.er_reject(statement text) RETURNS void LANGUAGE plpgsql AS $$BEGIN
 BEGIN EXECUTE statement;EXCEPTION WHEN OTHERS THEN RETURN;END;
 RAISE EXCEPTION 'Invalid report configuration accepted';
END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();u uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();cart uuid:=gen_random_uuid();oid uuid:=gen_random_uuid();r jsonb;batch jsonb;mail jsonb;cfg jsonb;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;start_at timestamptz:='2026-11-09T20:00:00Z';end_at timestamptz:='2026-11-10T20:00:00Z';
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Evening reports','audit-evening-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-evening-'||u||'@example.invalid','{}'),(sa,'audit-evening-'||sa||'@example.invalid','{}');
 UPDATE profiles SET campus_id=c,last_seen_at=NULL WHERE id IN(u,sa);
 UPDATE profiles SET role='super_admin' WHERE id=sa;
 cfg:='{"recipients":["ops@example.invalid"],"paid_order_alerts":false,"abandoned_cart_alerts":true,"daily_report":true,"weekly_report":false,"abandoned_minutes":30,"daily_report_time":"23:59"}';
 INSERT INTO system_settings(key,campus_id,value,is_public,updated_at) VALUES('campus_operations_email',c,cfg,false,now()-interval '1 day');
 IF (now() AT TIME ZONE 'Africa/Lagos')::time<'23:58'::time THEN
  PERFORM hg_capture_operations_emails(c);
  PERFORM pg_temp.er_check(NOT EXISTS(SELECT 1 FROM hg_internal.operations_emails WHERE campus_id=c AND kind='daily_report' AND reference=today::text),'no report before chosen time');
 END IF;
 IF (now() AT TIME ZONE 'Africa/Lagos')::time>='21:00'::time THEN
  UPDATE system_settings SET value=jsonb_set(value,'{daily_report_time}','"21:00"') WHERE campus_id=c AND key='campus_operations_email';
  PERFORM hg_capture_operations_emails(c);
  SELECT payload INTO r FROM hg_internal.operations_emails WHERE campus_id=c AND kind='daily_report' AND reference=today::text;
  PERFORM pg_temp.er_check(r IS NOT NULL AND (r->>'period_end')::timestamptz=(today+'21:00'::time) AT TIME ZONE 'Africa/Lagos','same-day report due at 9 PM WAT');
  PERFORM pg_temp.er_check((r->>'period_end')::timestamptz-(r->>'period_start')::timestamptz=interval '24 hours','complete 24-hour coverage');
  PERFORM hg_capture_operations_emails(c);
  PERFORM pg_temp.er_check((SELECT count(*)=1 FROM hg_internal.operations_emails WHERE campus_id=c AND kind='daily_report' AND reference=today::text),'daily dedupe after repeated scheduler scan');
 END IF;
 INSERT INTO wallet_transactions(user_id,campus_id,type,provider,reference_type,amount,balance_after,created_at) VALUES
 (u,c,'credit','paystack','topup',999,999,start_at-interval '1 second'),
 (u,c,'credit','paystack','topup',30,30,start_at),
 (u,c,'credit','paystack','topup',70,100,end_at-interval '1 second'),
 (u,c,'credit','paystack','topup',200,300,end_at),
 (sa,c,'credit','paystack','topup',500,500,end_at-interval '1 second');
 r:=hg_operations_summary_window(c,start_at,end_at);
 PERFORM pg_temp.er_check((r->>'wallet_funded')::numeric=100,'late-night funding included, next period boundary and test funds excluded');
 INSERT INTO orders(id,user_id,campus_id,status,payment_status,total_amount,card_amount_used,created_at) VALUES(oid,u,c,'received','pending',500,500,now()-interval '20 minutes');
 INSERT INTO abandoned_carts(id,user_id,campus_id,last_active_at,cart_payload) VALUES(cart,u,c,now()-interval '20 minutes',jsonb_build_object('pending_order_id',oid));
 PERFORM pg_temp.er_check(hg_operations_cart_alert_due(cart)>now(),'20-minute cart cannot alert');
 PERFORM hg_queue_operations_email(c,'abandoned_cart',cart::text,jsonb_build_object('cart_id',cart));
 batch:=hg_operations_email_outbox('claim',NULL,NULL,jsonb_build_object('campus_id',c));
 SELECT value INTO mail FROM jsonb_array_elements(batch) WHERE value->>'reference'=cart::text;
 PERFORM pg_temp.er_check(mail IS NOT NULL,'old early queued alert can be claimed');
 PERFORM pg_temp.er_check(hg_operations_email_outbox('begin',(mail->>'id')::uuid,(mail->>'token')::uuid) IS NULL,'send-time check defers early alert');
 PERFORM pg_temp.er_check((SELECT state='pending' AND available_at>now() FROM hg_internal.operations_emails WHERE id=(mail->>'id')::uuid),'early alert waits rather than disappearing or sending');
 UPDATE abandoned_carts SET last_active_at=now()-interval '40 minutes' WHERE id=cart;
 UPDATE orders SET created_at=now()-interval '40 minutes' WHERE id=oid;
 UPDATE profiles SET last_seen_at=now() WHERE id=u;
 PERFORM pg_temp.er_check(hg_operations_cart_alert_due(cart)>now(),'recent customer activity extends inactivity wait');
 UPDATE profiles SET last_seen_at=NULL WHERE id=u;
 PERFORM pg_temp.er_check(hg_operations_cart_alert_due(cart)<=now(),'idle unpaid cart becomes eligible after thirty minutes');
 UPDATE hg_internal.operations_emails SET available_at=now() WHERE id=(mail->>'id')::uuid;
 batch:=hg_operations_email_outbox('claim',NULL,NULL,jsonb_build_object('campus_id',c));
 SELECT value INTO mail FROM jsonb_array_elements(batch) WHERE value->>'reference'=cart::text;
 PERFORM pg_temp.er_check(hg_operations_email_outbox('begin',(mail->>'id')::uuid,(mail->>'token')::uuid) IS NOT NULL,'genuine inactive cart can send');
 UPDATE hg_internal.operations_emails SET state='claimed' WHERE id=(mail->>'id')::uuid;
 UPDATE orders SET payment_status='paid' WHERE id=oid;
 PERFORM pg_temp.er_check(hg_operations_email_outbox('begin',(mail->>'id')::uuid,(mail->>'token')::uuid) IS NULL,'payment immediately cancels queued recovery alert');
 PERFORM pg_temp.er_check((SELECT state='cancelled' FROM hg_internal.operations_emails WHERE id=(mail->>'id')::uuid),'paid customer receives no abandoned-cart email');
 PERFORM pg_temp.er_reject(format('UPDATE system_settings SET value=jsonb_set(value,''{abandoned_minutes}'',''10'') WHERE campus_id=%L AND key=''campus_operations_email''',c));
 PERFORM pg_temp.er_reject(format('UPDATE system_settings SET value=jsonb_set(value,''{daily_report_time}'',''"25:99"'') WHERE campus_id=%L AND key=''campus_operations_email''',c));
 RAISE NOTICE 'PASS: evening due/24-hour window/dedupe, exact funding boundaries, inactivity deferral, recent activity and paid-cart recheck, private settings validation';
END $test$;
ROLLBACK;
