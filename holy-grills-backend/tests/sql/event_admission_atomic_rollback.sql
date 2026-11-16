BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $test$
DECLARE c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); outsider uuid:=gen_random_uuid(); e uuid:=gen_random_uuid();
 t uuid:=gen_random_uuid(); guest uuid:=gen_random_uuid(); zero_t uuid:=gen_random_uuid(); zero_e uuid:=gen_random_uuid();
 legacy uuid:=gen_random_uuid(); m uuid:=gen_random_uuid(); result jsonb; again jsonb; balance integer; tracker integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Event','audit-event-'||c);
 INSERT INTO public.feature_flags(feature_name,campus_id,is_active) VALUES('events',c,true),('hp_multiplier',c,false);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-event-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Attendee"}'),(outsider,'audit-event-'||outsider||'@example.invalid','{"full_name":"[AUDIT rollback] Other"}');
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id IN(u,outsider);
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,hp_per_attendee,location)
 VALUES(e,'[AUDIT rollback] Event','audit-event-'||e,now()-interval '1 hour',now()+interval '1 day',true,c,50,'FUTA'),
 (zero_e,'[AUDIT rollback] Zero','audit-event-'||zero_e,now()-interval '1 hour',now()+interval '1 day',true,c,0,'FUTA');
 INSERT INTO public.event_door_tokens(event_id,qr_token) VALUES(e,'audit-door'),(zero_e,'audit-zero-door');
 INSERT INTO public.event_tickets(id,event_id,user_id,status,payment_status,campus_id) VALUES(t,e,u,'confirmed','paid',c),(zero_t,zero_e,u,'confirmed','not_required',c);
 INSERT INTO public.event_tickets(id,event_id,is_guest,guest_email,status,payment_status,campus_id) VALUES(guest,e,true,'audit-guest@example.invalid','confirmed','paid',c);
 INSERT INTO public.milestones(id,title,trigger_type,trigger_value,hp_awarded,is_active,campus_id)
 VALUES(m,'[AUDIT rollback] First event','first_event',1,20,true,c);
 SELECT hp_balance INTO balance FROM public.profiles WHERE id=u;
 SELECT coalesce(sum(total_earned),0) INTO tracker FROM public.monthly_hp_tracker WHERE user_id=u;
 BEGIN
  PERFORM public.hg_admit_event_ticket(e,t,u,'wrong-door',c,50);
  RAISE EXCEPTION 'TEST invalid door accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.hg_admit_event_ticket(e,t,outsider,'audit-door',c,50);
  RAISE EXCEPTION 'TEST foreign owner accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 -- Inject a process-equivalent transactional failure after all financial work.
 BEGIN
  PERFORM public.hg_admit_event_ticket(e,t,u,'audit-door',c,50);
  RAISE EXCEPTION 'controlled interruption';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled interruption' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.event_checkins WHERE ticket_id=t) OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=u)
 OR EXISTS(SELECT 1 FROM public.user_milestones WHERE user_id=u) THEN RAISE EXCEPTION 'TEST interrupted admission left partial state'; END IF;
 result:=public.hg_admit_event_ticket(e,t,u,'audit-door',c,50);
 IF (result->>'hp_added_to_active')::integer<>50 OR (result->>'hp_added_to_pending')::integer<>0 THEN RAISE EXCEPTION 'TEST active receipt wrong'; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>balance+70 THEN RAISE EXCEPTION 'TEST HP including milestone wrong'; END IF;
 IF (SELECT sum(total_earned) FROM public.monthly_hp_tracker WHERE user_id=u)<>tracker+70 THEN RAISE EXCEPTION 'TEST tracker wrong'; END IF;
 UPDATE public.events SET hp_per_attendee=999 WHERE id=e;
 UPDATE public.milestones SET hp_awarded=999 WHERE id=m;
 again:=public.hg_admit_event_ticket(e,t,u,'audit-door',c,50);
 IF NOT (again->>'replayed')::boolean OR (again->>'hp_added_to_active')::integer<>50
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>balance+70 THEN RAISE EXCEPTION 'TEST committed-response retry changed rewards'; END IF;
 result:=public.hg_admit_event_ticket(zero_e,zero_t,u,'audit-zero-door',c,50);
 UPDATE public.events SET hp_per_attendee=500 WHERE id=zero_e;
 again:=public.hg_admit_event_ticket(zero_e,zero_t,u,'audit-zero-door',c,50);
 IF (again->>'hp_added_to_active')::integer<>0 THEN RAISE EXCEPTION 'TEST zero receipt mutated'; END IF;
 result:=public.hg_admit_event_ticket(e,guest,NULL,'audit-door',c,50);
 IF NOT (result->>'is_guest')::boolean OR (result->>'hp_added_to_active')::integer<>0 THEN RAISE EXCEPTION 'TEST guest got unowned HP'; END IF;
 IF (SELECT count(*) FROM public.hp_transactions WHERE user_id=u)<>2 THEN RAISE EXCEPTION 'TEST duplicate ledger'; END IF;
 -- A historical ledger is linked at its original amount without a second credit/counter.
 UPDATE public.milestones SET is_active=false WHERE id=m;
 INSERT INTO public.event_tickets(id,event_id,user_id,status,payment_status,campus_id) VALUES(legacy,e,outsider,'confirmed','paid',c);
 INSERT INTO public.event_checkins(ticket_id,checked_in_by,qr_code,campus_id) VALUES(legacy,outsider,'audit-door',c);
 PERFORM public.record_hp_transaction_atomic(outsider,25,'earn','active','event','event',e,NULL,'Historical event',c);
 SELECT hp_balance INTO balance FROM public.profiles WHERE id=outsider;
 result:=public.hg_admit_event_ticket(e,legacy,outsider,'audit-door',c,50);
 IF (result->>'hp_added_to_active')::integer<>25 OR (SELECT hp_balance FROM public.profiles WHERE id=outsider)<>balance
 OR (SELECT hp_transaction_id IS NULL FROM public.event_checkins WHERE ticket_id=legacy) THEN RAISE EXCEPTION 'TEST historical ledger re-awarded'; END IF;
 UPDATE public.event_tickets SET payment_status='pending'  WHERE id=guest;
 BEGIN
  PERFORM public.hg_admit_event_ticket(e,guest,NULL,'audit-door',c,50);
  RAISE EXCEPTION 'TEST unpaid replay accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 IF has_function_privilege('anon','public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_complete_event_milestones(uuid,numeric)','EXECUTE')
 OR has_table_privilege('authenticated','public.event_checkins','INSERT') THEN RAISE EXCEPTION 'TEST public admission mutation'; END IF;
END $test$;
ROLLBACK;
SELECT 'PASS: atomic event admission/HP/milestones/tracker, interruption rollback, durable replay, changed configuration, zero reward, guest ownership, invalid door/owner/payment and service-only privilege; all fixtures rolled back' AS evidence;
