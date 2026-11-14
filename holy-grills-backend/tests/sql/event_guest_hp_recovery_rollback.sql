BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();u uuid:=gen_random_uuid();v uuid:=gen_random_uuid();z uuid:=gen_random_uuid();e uuid:=gen_random_uuid();e2 uuid:=gen_random_uuid();e3 uuid:=gen_random_uuid();t uuid:=gen_random_uuid();legacy uuid:=gen_random_uuid();zt uuid:=gen_random_uuid();r jsonb;email text:='audit-guest-hp-'||gen_random_uuid()||'@example.invalid';email2 text:='audit-legacy-hp-'||gen_random_uuid()||'@example.invalid';email3 text:='audit-zero-hp-'||gen_random_uuid()||'@example.invalid';
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Guest HP','audit-'||c);
 INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES('events',true,c),('hp_multiplier',false,c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-'||a||'@example.invalid','{"full_name":"Audit admin"}');UPDATE profiles SET role='admin',campus_id=c,is_active=true WHERE id=a;
 INSERT INTO events(id,title,slug,location,starts_at,ends_at,campus_id,is_published,hp_per_attendee) VALUES
 (e,'[AUDIT rollback] Guest HP','audit-'||e,'Hall',now()-interval '1 hour',now()+interval '1 day',c,true,50),
 (e2,'[AUDIT rollback] Legacy HP','audit-'||e2,'Hall',now()-interval '1 hour',now()+interval '1 day',c,true,70),
 (e3,'[AUDIT rollback] Zero HP','audit-'||e3,'Hall',now()-interval '1 hour',now()+interval '1 day',c,true,0);
 INSERT INTO event_door_tokens(event_id,qr_token) VALUES(e,'audit-door'),(e3,'audit-zero');
 INSERT INTO event_tickets(id,event_id,is_guest,guest_email,guest_name,status,payment_status,campus_id) VALUES(t,e,true,email,'Audit guest','confirmed','not_required',c),(legacy,e2,true,email2,'Audit legacy','confirmed','not_required',c),(zt,e3,true,email3,'Audit zero','confirmed','not_required',c);
 r:=hg_admit_event_ticket(e,t,null,'audit-door',c,50);
 IF (r->>'claimable_hp')::integer<>50 OR (r->>'hp_added_to_active')::integer<>0 THEN RAISE EXCEPTION 'Guest attendance snapshot incorrect';END IF;
 UPDATE events SET hp_per_attendee=500 WHERE id=e;
 INSERT INTO event_checkins(ticket_id,campus_id,qr_code,reward_receipt) VALUES(legacy,c,legacy::text,'{"is_guest":true,"completed":true,"hp_added_to_active":0}');
 PERFORM hg_admit_event_ticket(e3,zt,null,'audit-zero',c,50);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,email,'{"full_name":"Audit guest"}'),(v,email2,'{"full_name":"Audit legacy"}'),(z,email3,'{"full_name":"Audit zero"}');UPDATE profiles SET campus_id=c,is_active=true WHERE id IN(u,v,z);
 r:=hg_claim_guest_attendance_hp(u);IF (r->>'claimed')::integer<>0 THEN RAISE EXCEPTION 'Unverified account claimed HP';END IF;
 UPDATE auth.users SET email_confirmed_at=now() WHERE id IN(u,v,z);
 -- Privileged synthetic clock movement only; no application edit bypass.
 PERFORM set_config('hg.event_operation',e::text,true);UPDATE events SET ends_at=now()-interval '1 minute' WHERE id=e;PERFORM set_config('hg.event_operation','',true);
 EXECUTE 'SET LOCAL ROLE service_role';
 r:=hg_claim_guest_attendance_hp(u);
 EXECUTE 'RESET ROLE';
 IF (r->>'claimed')::integer<>1 OR NOT EXISTS(SELECT 1 FROM hp_transactions WHERE user_id=u AND reference_type='event' AND reference_id=e AND amount=50 AND status='active') THEN RAISE EXCEPTION 'Earned HP snapshot was lost after event/configuration change';END IF;
 r:=hg_claim_guest_attendance_hp(u);IF (r->>'claimed')::integer<>0 OR (SELECT count(*) FROM hp_transactions WHERE user_id=u AND reference_type='event' AND reference_id=e)<>1 THEN RAISE EXCEPTION 'Guest HP replay awarded twice';END IF;
 r:=hg_claim_guest_attendance_hp(v);IF (r->>'review')::integer<>1 OR NOT EXISTS(SELECT 1 FROM event_checkins WHERE ticket_id=legacy AND reward_receipt->>'guest_claim_state'='review_required') THEN RAISE EXCEPTION 'Legacy HP amount was guessed';END IF;
 BEGIN PERFORM hg_review_guest_attendance_hp(u,e2,legacy,70,'Verified original event promise');RAISE EXCEPTION 'Student reviewed HP';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 r:=hg_review_guest_attendance_hp(a,e2,legacy,70,'Verified original event promise');IF (r->>'hp_added_to_active')::integer<>70 THEN RAISE EXCEPTION 'Admin guest HP review failed';END IF;
 r:=hg_review_guest_attendance_hp(a,e2,legacy,70,'Verified original event promise');IF NOT (r->>'replayed')::boolean THEN RAISE EXCEPTION 'Admin review replay missing';END IF;
 BEGIN PERFORM hg_review_guest_attendance_hp(a,e2,legacy,80,'Different amount on retry');RAISE EXCEPTION 'Changed review intent awarded again';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_GUEST_HP_CONFLICT' THEN RAISE;END IF;END;
 r:=hg_claim_guest_attendance_hp(z);IF (r->>'claimed')::integer<>1 OR EXISTS(SELECT 1 FROM hp_transactions WHERE user_id=z AND reference_type='event' AND reference_id=e3) THEN RAISE EXCEPTION 'Zero-HP admission invented an event award';END IF;
 IF has_function_privilege('authenticated','public.hg_claim_guest_attendance_hp(uuid)','execute') OR has_function_privilege('anon','public.hg_review_guest_attendance_hp(uuid,uuid,uuid,integer,text)','execute') THEN RAISE EXCEPTION 'Guest HP helper exposed';END IF;
END $$;
ROLLBACK;
