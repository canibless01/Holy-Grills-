BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();r uuid:=gen_random_uuid();rows jsonb;receipt jsonb;birthday jsonb;first_id uuid;first_token uuid;
BEGIN
 INSERT INTO public.campuses(id,name,slug,is_active) VALUES(c,'[AUDIT rollback] Mail recovery','audit-'||c,true);
 INSERT INTO public.system_settings(key,campus_id,value,is_public) VALUES('campus_operations_email',c,'{"recipients":["outbox@example.invalid"],"paid_order_alerts":false,"abandoned_cart_alerts":false,"daily_report":false,"weekly_report":false,"abandoned_minutes":30,"daily_report_time":"21:00"}',false);
 INSERT INTO public.catering_requests(id,campus_id,organizer_name,email,phone,event_name,event_date,expected_guests) VALUES(r,c,'Rollback guest','guest@example.invalid','08012345678','Rollback event',current_date+10,10);
 -- The old API still sends its legacy thread during rolling deployment; it must not also queue mail.
 UPDATE public.catering_requests SET status='quoted',updated_at=now() WHERE id=r;
 IF EXISTS(SELECT 1 FROM hg_internal.operations_emails WHERE campus_id=c AND kind='catering_status') THEN RAISE EXCEPTION 'Legacy deployment double send';END IF;
 PERFORM set_config('request.headers','{"x-hg-write-protocol":"catering-status-v1"}',true);
 UPDATE public.catering_requests SET status='confirmed',quoted_amount=0,updated_at=now()+interval '1 second' WHERE id=r;
 IF (SELECT count(*) FROM hg_internal.operations_emails WHERE campus_id=c AND kind='catering_status')<>1 THEN RAISE EXCEPTION 'Status intent missing';END IF;
 UPDATE public.catering_requests SET status=status,notes='Private note',updated_at=now()+interval '2 seconds' WHERE id=r;
 IF (SELECT count(*) FROM hg_internal.operations_emails WHERE campus_id=c AND kind='catering_status')<>1 THEN RAISE EXCEPTION 'No-op status duplicated';END IF;
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c,'catering_request_id',r));
 IF jsonb_array_length(rows)<>1 THEN RAISE EXCEPTION 'Bounded catering claim missing';END IF;
 receipt:=rows->0;first_id:=(receipt->>'id')::uuid;first_token:=(receipt->>'token')::uuid;
 UPDATE hg_internal.operations_emails SET lease_until=now()-interval '1 second' WHERE id=first_id;
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c,'catering_request_id',r));
 IF jsonb_array_length(rows)<>1 THEN RAISE EXCEPTION 'Crashed preparation did not recover';END IF;
 IF public.hg_operations_email_outbox('begin',first_id,first_token) IS NOT NULL THEN RAISE EXCEPTION 'Expired owner regained delivery';END IF;
 first_token:=(rows->0->>'token')::uuid;

 -- A later status makes the prepared earlier email stale before provider handoff.
 UPDATE public.catering_requests SET status='cancelled',updated_at=now()+interval '3 seconds' WHERE id=r;
 IF public.hg_operations_email_outbox('begin',first_id,first_token) IS NOT NULL THEN RAISE EXCEPTION 'Superseded catering status sent';END IF;
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c,'catering_request_id',r));
 IF jsonb_array_length(rows)<>1 THEN RAISE EXCEPTION 'Replacement status missing';END IF;
 receipt:=rows->0;
 IF public.hg_operations_email_outbox('begin',(receipt->>'id')::uuid,(receipt->>'token')::uuid) IS NULL THEN RAISE EXCEPTION 'Current catering status blocked by operator recipient config';END IF;
 PERFORM public.hg_operations_email_outbox('finish',(receipt->>'id')::uuid,(receipt->>'token')::uuid,'{"state":"uncertain","receipt":{"error":"lost response"}}');
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c));
 IF jsonb_array_length(rows)<>0 THEN RAISE EXCEPTION 'Uncertain email blindly retried';END IF;
 -- Missing optional birthday switch means enabled at both capture AND final handoff.
 PERFORM public.hg_queue_birthday_reports(c);
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c));
 IF jsonb_array_length(rows)<>1 OR rows->0->>'kind'<>'birthday_report' THEN RAISE EXCEPTION 'Default birthday capture missing';END IF;
 birthday:=rows->0;
 IF public.hg_operations_email_outbox('begin',(birthday->>'id')::uuid,(birthday->>'token')::uuid) IS NULL THEN RAISE EXCEPTION 'Default-on birthday report cancelled at handoff';END IF;
 PERFORM public.hg_operations_email_outbox('finish',(birthday->>'id')::uuid,(birthday->>'token')::uuid,'{"state":"accepted","receipt":{}}');
 UPDATE public.system_settings SET value=value||'{"birthday_report":false}' WHERE key='campus_operations_email' AND campus_id=c;
 INSERT INTO hg_internal.operations_emails(campus_id,kind,reference,recipient,payload) VALUES(c,'birthday_report','optout-check','outbox@example.invalid','{}');
 rows:=public.hg_operations_email_outbox('claim',null,null,jsonb_build_object('campus_id',c));
 IF jsonb_array_length(rows)<>1 THEN RAISE EXCEPTION 'Optout test intent missing';END IF;
 receipt:=rows->0;
 IF public.hg_operations_email_outbox('begin',(receipt->>'id')::uuid,(receipt->>'token')::uuid) IS NOT NULL THEN RAISE EXCEPTION 'Explicit birthday-report optout ignored';END IF;
 -- No direct anonymous/member submission can bypass API validation and its rate limit.
 IF has_any_column_privilege('anon','public.catering_requests','INSERT') OR has_any_column_privilege('authenticated','public.catering_requests','INSERT') THEN RAISE EXCEPTION 'Direct catering insert remains exposed';END IF;
 IF NOT has_table_privilege('service_role','public.catering_requests','INSERT') THEN RAISE EXCEPTION 'Service submission broken';END IF;
 IF has_function_privilege('authenticated','hg_internal.capture_catering_status_email()','EXECUTE') THEN RAISE EXCEPTION 'Private capture helper exposed';END IF;
END$$;
ROLLBACK;
