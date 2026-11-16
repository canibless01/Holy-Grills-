BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();o uuid:=gen_random_uuid();e uuid:=gen_random_uuid();t uuid:=gen_random_uuid();t2 uuid:=gen_random_uuid();r jsonb;audits integer;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Opening','audit-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-'||a||'@example.invalid','{}'),(o,'audit-'||o||'@example.invalid','{}');UPDATE profiles SET campus_id=c,is_active=true WHERE id IN(a,o);UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='event_organizer' WHERE id=o;
 INSERT INTO feature_flags(feature_name,campus_id,is_active) VALUES('events',c,true),('hp_multiplier',c,false);
 INSERT INTO events(id,title,slug,location,starts_at,ends_at,is_published,campus_id,organizer_id,hp_per_attendee) VALUES(e,'[AUDIT rollback] Opening','audit-'||e,'Hall',now()+interval '1 hour',now()+interval '3 hours',true,c,o,50);
 INSERT INTO event_door_tokens(event_id,qr_token) VALUES(e,'audit-door');
 INSERT INTO event_tickets(id,event_id,is_guest,guest_email,status,payment_status,campus_id) VALUES(t,e,true,'audit-a@example.invalid','confirmed','not_required',c),(t2,e,true,'audit-b@example.invalid','confirmed','not_required',c);
 BEGIN PERFORM hg_set_event_admission_window(o,e,30);RAISE EXCEPTION 'Organizer changed admission terms';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 EXECUTE 'SET LOCAL ROLE service_role';r:=hg_set_event_admission_window(a,e,30);EXECUTE 'RESET ROLE';
 SELECT count(*) INTO audits FROM admin_audit_logs WHERE entity_id=e::text AND action='admission_window_changed';
 r:=hg_set_event_admission_window(a,e,30);IF NOT(r->>'replayed')::boolean OR (SELECT count(*) FROM admin_audit_logs WHERE entity_id=e::text AND action='admission_window_changed')<>audits THEN RAISE EXCEPTION 'Setting retry duplicated audit';END IF;
 BEGIN PERFORM hg_admit_event_ticket(e,t,a,null,c,50);RAISE EXCEPTION 'Staff admitted before opening';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_ADMISSION_NOT_OPEN' THEN RAISE;END IF;END;
 BEGIN PERFORM hg_admit_event_ticket(e,t,null,'audit-door',c,50);RAISE EXCEPTION 'Self scan admitted before opening';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_ADMISSION_NOT_OPEN' THEN RAISE;END IF;END;
 IF EXISTS(SELECT 1 FROM event_checkins WHERE ticket_id IN(t,t2)) THEN RAISE EXCEPTION 'Early admission wrote receipt';END IF;
 -- Approved reschedule clock movement in this synthetic rollback fixture.
 PERFORM set_config('hg.event_operation',e::text,true);UPDATE events SET starts_at=now()-interval '1 hour',ends_at=now()+interval '1 hour' WHERE id=e;PERFORM set_config('hg.event_operation','',true);
 r:=hg_admit_event_ticket(e,t,a,null,c,50);IF NOT(r->>'completed')::boolean THEN RAISE EXCEPTION 'Staff admission did not follow reschedule';END IF;
 r:=hg_admit_event_ticket(e,t2,null,'audit-door',c,50);IF NOT(r->>'completed')::boolean THEN RAISE EXCEPTION 'Self scan did not follow reschedule';END IF;
 r:=hg_admit_event_ticket(e,t,a,null,c,50);IF NOT(r->>'replayed')::boolean THEN RAISE EXCEPTION 'Existing admission did not replay';END IF;
 BEGIN PERFORM hg_set_event_admission_window(a,e,null);RAISE EXCEPTION 'Admission schedule changed after attendance';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_ADMISSION_WINDOW_LOCKED' THEN RAISE;END IF;END;
 PERFORM set_config('hg.event_operation',e::text,true);UPDATE events SET ends_at=now()-interval '1 minute' WHERE id=e;PERFORM set_config('hg.event_operation','',true);
 BEGIN PERFORM hg_admit_event_ticket(e,t,a,null,c,50);RAISE EXCEPTION 'Ended event admitted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'Event not available' THEN RAISE;END IF;END;
 IF has_function_privilege('authenticated','public.hg_set_event_admission_window(uuid,uuid,integer)','execute') OR has_function_privilege('anon','public.hg_set_event_admission_window(uuid,uuid,integer)','execute') THEN RAISE EXCEPTION 'Admission settings exposed';END IF;
END $$;
ROLLBACK;
