BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); e uuid:=gen_random_uuid(); empty_e uuid:=gen_random_uuid(); t uuid:=gen_random_uuid(); empty_t uuid:=gen_random_uuid(); ticket uuid:=gen_random_uuid();n integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Event history','audit-event-history-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-event-history-'||a||'@example.invalid','{}');
 UPDATE public.profiles SET role='admin',campus_id=c WHERE id=a;
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,location) VALUES(e,'[AUDIT rollback] Issued','audit-event-history-'||e,now(),now()+interval '1 day',true,c,'FUTA'),(empty_e,'[AUDIT rollback] Empty','audit-event-history-'||empty_e,now(),now()+interval '1 day',false,c,'FUTA');
 INSERT INTO public.event_ticket_tiers(id,event_id,name,campus_id) VALUES(t,e,'Issued',c),(empty_t,e,'Empty',c);
 INSERT INTO public.event_tickets(id,event_id,tier_id,is_guest,guest_email,status,payment_status,campus_id) VALUES(ticket,e,t,true,'audit-event-history@example.invalid','confirmed','paid',c);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 BEGIN DELETE FROM public.events WHERE id=e;RAISE EXCEPTION 'issued event history destroyed';EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN DELETE FROM public.event_ticket_tiers WHERE id=t;RAISE EXCEPTION 'issued tier history destroyed';EXCEPTION WHEN check_violation THEN NULL;END;
 UPDATE public.events SET is_published=false WHERE id=e;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'unpublish blocked';END IF;
 UPDATE public.event_ticket_tiers SET is_active=false WHERE id=t;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'stop tier sales blocked';END IF;
 DELETE FROM public.event_ticket_tiers WHERE id=empty_t;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'empty tier removal blocked';END IF;
 DELETE FROM public.events WHERE id=empty_e;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'empty event removal blocked';END IF;
 PERFORM set_config('role','none',true);
 IF NOT EXISTS(SELECT 1 FROM public.event_tickets WHERE id=ticket AND tier_id=t) THEN RAISE EXCEPTION 'ticket history changed';END IF;
 IF has_function_privilege('anon','public.hg_guard_issued_event_history()','EXECUTE') OR has_function_privilege('authenticated','public.hg_guard_issued_event_history()','EXECUTE') THEN RAISE EXCEPTION 'trigger exposed as RPC';END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: direct admin issued event/tier deletion denied, unpublish/stop-sales and empty removal work; ticket history retained; trigger is private' AS evidence;
