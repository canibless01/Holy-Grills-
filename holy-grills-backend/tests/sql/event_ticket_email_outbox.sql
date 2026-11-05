BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); paid_e uuid:=gen_random_uuid(); free_e uuid:=gen_random_uuid(); tier uuid:=gen_random_uuid();
 guest uuid; member uuid; historical uuid; pending uuid; admin uuid:=gen_random_uuid(); result jsonb; again jsonb; claim jsonb; token uuid; saved_key text;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Ticket mail','audit-ticket-mail-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-ticket-mail-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Member"}'),(admin,'audit-ticket-mail-'||admin||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id=u;
 UPDATE public.profiles SET campus_id=c,role='admin' WHERE id=admin;
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,location,capacity)
 VALUES(paid_e,'Paid snapshot','audit-ticket-mail-'||paid_e,now(),now()+interval '1 day',true,c,'FUTA',20),
 (free_e,'Free snapshot','audit-ticket-mail-'||free_e,now(),now()+interval '1 day',true,c,'FUTA',20);
 INSERT INTO public.event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,capacity,campus_id) VALUES(tier,paid_e,'Paid',1000,1000,20,c);
 result:=public.hg_register_guest_event_with_delivery(free_e,'GUEST@example.invalid','Guest','08012345678',NULL,NULL,'{}');
 guest:=(result->>'ticket_id')::uuid;
 IF guest IS NULL OR NOT EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=guest AND user_id IS NULL AND notification_id IS NULL
 AND channel='email' AND status='queued' AND dispatch_payload->>'kind'='event_ticket_email'
 AND dispatch_payload->'notification'->>'email'='guest@example.invalid') THEN RAISE EXCEPTION 'free guest ticket/mail not saved together'; END IF;
 saved_key:=(SELECT dispatch->>'key' FROM public.notification_deliveries WHERE id=guest);
 again:=public.hg_register_guest_event_with_delivery(free_e,'guest@example.invalid','Guest','08012345678',NULL,NULL,'{}');
 IF again->>'ticket_id'<>guest::text OR (SELECT count(*) FROM public.notification_deliveries WHERE id=guest)<>1 THEN RAISE EXCEPTION 'guest registration replay duplicated email'; END IF;
 result:=public.hg_register_event_with_delivery(free_e,u,NULL,false,0,NULL,'{}'); member:=(result->>'ticket_id')::uuid;
 IF NOT EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=member AND user_id=u AND dispatch_payload->'notification'->>'email'='audit-ticket-mail-'||u||'@example.invalid') THEN RAISE EXCEPTION 'member ticket email not captured'; END IF;
 -- Unversioned historical mail is never backfilled by a repeated registration.
 result:=public.register_for_event_guest_paid(free_e,'historical@example.invalid','Old guest','08012345678',NULL,NULL,'{}'); historical:=(result->>'ticket_id')::uuid;
 PERFORM public.hg_register_guest_event_with_delivery(free_e,'historical@example.invalid','Old guest','08012345678',NULL,NULL,'{}');
 IF EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=historical) THEN RAISE EXCEPTION 'historical ticket replayed mail'; END IF;
 result:=public.hg_register_guest_event_with_delivery(paid_e,'payer@example.invalid','Payer','08012345678',tier,NULL,'{}'); pending:=(result->>'ticket_id')::uuid;
 IF EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=pending) THEN RAISE EXCEPTION 'unpaid ticket mailed'; END IF;
 BEGIN PERFORM public.hg_pay_event_with_delivery(pending,'paystack','AUDIT-TICKET-'||pending,999,'{}'); RAISE EXCEPTION 'TEST incorrect amount accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 BEGIN PERFORM public.hg_pay_event_with_delivery(pending,'paystack','AUDIT-TICKET-'||pending,1000,'{}'); RAISE EXCEPTION 'controlled crash'; EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled crash' THEN RAISE; END IF; END;
 IF (SELECT payment_status FROM public.event_tickets WHERE id=pending)<>'pending' OR EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=pending)
 OR EXISTS(SELECT 1 FROM public.payments WHERE ticket_id=pending) THEN RAISE EXCEPTION 'interrupted payment left partial ticket/mail'; END IF;
 PERFORM public.hg_pay_event_with_delivery(pending,'paystack','AUDIT-TICKET-'||pending,1000,'{}');
 PERFORM public.hg_pay_event_with_delivery(pending,'paystack','AUDIT-TICKET-'||pending,1000,'{}');
 IF (SELECT payment_status FROM public.event_tickets WHERE id=pending)<>'paid' OR (SELECT count(*) FROM public.notification_deliveries WHERE id=pending)<>1
 OR (SELECT count(*) FROM public.payments WHERE ticket_id=pending)<>1 THEN RAISE EXCEPTION 'payment/mail replay duplicated or missing'; END IF;
 UPDATE public.events SET title='Changed after purchase' WHERE id=free_e;
 PERFORM public.hg_queue_event_ticket_email(guest);
 IF (SELECT dispatch->>'key' FROM public.notification_deliveries WHERE id=guest)<>saved_key
 OR (SELECT dispatch_payload->'notification'->'metadata'->>'event_title' FROM public.notification_deliveries WHERE id=guest)<>'Free snapshot' THEN RAISE EXCEPTION 'queued promise changed after event edit'; END IF;
 -- Old workers ignore raw ticket rows instead of claiming/skipping guest mail.
 IF public.hg_claim_notification_dispatch(guest)->>'state'<>'missing' THEN RAISE EXCEPTION 'old worker claimed new raw delivery'; END IF;
 claim:=public.hg_claim_notification_dispatch_v2(guest); token:=(claim->>'token')::uuid;
 IF claim->>'state'<>'claimed' OR claim->'payload'->>'ticket_id'<>guest::text THEN RAISE EXCEPTION 'new worker cannot recover guest email'; END IF;
 PERFORM public.hg_begin_notification_dispatch(guest,token,'{"to_email":"guest@example.invalid","html_body":"Frozen"}');
 UPDATE public.notification_deliveries SET dispatch=jsonb_set(dispatch,'{lease_until}',to_jsonb(now()-interval '1 minute')) WHERE id=guest;
 IF public.hg_claim_notification_dispatch_v2(guest)->>'state'<>'uncertain' THEN RAISE EXCEPTION 'uncertain guest email blindly retried'; END IF;
 result:=public.hg_reconcile_notification_dispatch(admin,guest,gen_random_uuid(),'sent','onesignal','actual-provider-id','Provider log confirms accepted guest ticket');
 IF result->>'status'<>'sent' THEN RAISE EXCEPTION 'guest delivery review failed'; END IF;
 IF has_function_privilege('anon','public.hg_register_guest_event_with_delivery(uuid,extensions.citext,text,text,uuid,uuid,jsonb)','execute')
 OR has_function_privilege('authenticated','public.hg_pay_event_with_delivery(uuid,text,text,numeric,jsonb)','execute')
 OR has_function_privilege('authenticated','public.hg_claim_notification_dispatch_v2(uuid)','execute') THEN RAISE EXCEPTION 'ticket mail RPC publicly executable'; END IF;
END $verify$;
SET LOCAL ROLE authenticated;
DO $privacy$ BEGIN IF EXISTS(SELECT 1 FROM public.notification_deliveries WHERE dispatch_payload->>'kind'='event_ticket_email') THEN RAISE EXCEPTION 'guest ticket secret exposed'; END IF; END $privacy$;
RESET ROLE;
ROLLBACK;
SELECT 'PASS: free guest/member and paid ticket/email capture, atomic rollback, paid/repeated callbacks, historical isolation, immutable content, guest claim/uncertainty/review and private grants/RLS; no provider sends; all fixtures rolled back' AS evidence;
