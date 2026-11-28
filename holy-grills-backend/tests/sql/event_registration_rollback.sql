BEGIN;
SET LOCAL request.jwt.claim.role='service_role';
SET LOCAL search_path=public,extensions;
DO $$
DECLARE c uuid:=gen_random_uuid();o uuid:=gen_random_uuid();u uuid:=gen_random_uuid();bad uuid:=gen_random_uuid();e uuid:=gen_random_uuid();free uuid:=gen_random_uuid();support uuid:=gen_random_uuid();guest_ticket uuid;r jsonb;d jsonb;
 email text:='audit-event-'||gen_random_uuid()::text||'@example.invalid';
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(c,'[AUDIT rollback] Event registration','audit-'||c,true);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(o,'audit-'||o||'@example.invalid',jsonb_build_object('full_name','Organizer','campus_id',c));
 INSERT INTO profiles(id,email,full_name,role,campus_id,is_active) VALUES(o,'audit-'||o||'@example.invalid','Organizer','event_organizer',c,true) ON CONFLICT(id) DO UPDATE SET role='event_organizer',campus_id=c,is_active=true;
 d:=jsonb_build_object('title','Community launch','description',E'Paragraph one\n\nParagraph two','location','Hall','starts_at',now()+interval '2 days','ends_at',now()+interval '3 days','capacity',10,'registration_fields',jsonb_build_array(jsonb_build_object('name','department','label','Department','type','text','required',true)));
 r:=hg_organizer_event_draft(o,e,'create',d);
 IF (r->'registration_fields'->0->>'name')<>'department' OR r->>'description'<>E'Paragraph one\n\nParagraph two' OR r->>'slug' LIKE 'organizer-%' THEN RAISE EXCEPTION 'Draft question/paragraph/link save failed';END IF;
 r:=hg_organizer_event_draft(o,e,'create',d);
 IF (SELECT count(*) FROM events WHERE id=e)<>1 THEN RAISE EXCEPTION 'Draft retry duplicate';END IF;
 r:=hg_organizer_event_draft(o,e,'edit',d||'{"capacity":20}');
 IF (SELECT capacity FROM events WHERE id=e)<>20 OR (SELECT registration_fields->0->>'name' FROM events WHERE id=e)<>'department' THEN RAISE EXCEPTION 'Draft edit lost fields';END IF;
 UPDATE events SET review_status='approved',is_published=true,is_paid=false WHERE id=e;
 INSERT INTO event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,price_hp,capacity,campus_id) VALUES(free,e,'Free admission',0,0,0,10,c),(support,e,'Optional support',200,200,0,10,c);
 r:=hg_register_guest_event_with_delivery(e,email::citext,'Free guest','08012345678',free,null,'{"registration_answers":{"department":"Computing"}}');guest_ticket:=(r->>'ticket_id')::uuid;
 IF r->>'payment_status'<>'not_required' OR coalesce((r->>'card_amount_used')::numeric,0)<>0 THEN RAISE EXCEPTION 'Free tier charged: %',r;END IF;
 r:=hg_register_guest_event_with_delivery(e,('audit-support-'||e||'@example.invalid')::citext,'Support guest','08012345678',support,null,'{}');
 IF r->>'payment_status'<>'pending' OR (r->>'card_amount_used')::numeric<>200 THEN RAISE EXCEPTION 'Support tier incorrectly free: %',r;END IF;
 r:=hg_organizer_event_attendees(o,e,'Free guest',50,0);
 IF r->0->'registration_answers'->>'department'<>'Computing' THEN RAISE EXCEPTION 'Answers missing from organizer roster: %',r;END IF;
 -- An unverified account cannot capture an existing guest booking.
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(bad,email,jsonb_build_object('full_name','Unverified','campus_id',c));
 INSERT INTO profiles(id,email,full_name,role,campus_id,is_active) VALUES(bad,email,'Unverified','student',c,true) ON CONFLICT(id) DO UPDATE SET campus_id=c,is_active=true;
 IF hg_link_verified_event_tickets(bad)<>0 OR (SELECT user_id FROM event_tickets WHERE id=guest_ticket) IS NOT NULL THEN RAISE EXCEPTION 'Unverified account captured ticket';END IF;
 -- Confirmation is authoritative in auth.users, not editable profile metadata.
 UPDATE auth.users SET email_confirmed_at=now() WHERE id=bad;
 EXECUTE 'SET LOCAL ROLE service_role';
 r:=to_jsonb(hg_link_verified_event_tickets(bad));
 EXECUTE 'RESET ROLE';
 IF r<>'1'::jsonb OR (SELECT user_id FROM event_tickets WHERE id=guest_ticket) IS DISTINCT FROM bad THEN RAISE EXCEPTION 'Verified guest linkage failed: count %, ticket %, profile %',r,(SELECT jsonb_build_object('user',user_id,'guest',is_guest,'status',status) FROM event_tickets WHERE id=guest_ticket),(SELECT jsonb_build_object('active',is_active) FROM profiles WHERE id=bad);END IF;
 IF hg_link_verified_event_tickets(bad)<>0 THEN RAISE EXCEPTION 'Verified linkage replay changed ownership';END IF;
 IF has_function_privilege('anon','public.hg_link_verified_event_tickets(uuid)','execute') OR has_function_privilege('authenticated','public.hg_link_verified_event_tickets(uuid)','execute') THEN RAISE EXCEPTION 'Guest linking helper exposed';END IF;
 PERFORM set_config('audit.event_claim_actor',bad::text,true);
 IF hg_event_attendance_count(e)<>0 THEN RAISE EXCEPTION 'Incorrect attendance count';END IF;
END $$;
SET LOCAL ROLE service_role;
SELECT public.hg_link_verified_event_tickets(current_setting('audit.event_claim_actor')::uuid);
RESET ROLE;
ROLLBACK;
