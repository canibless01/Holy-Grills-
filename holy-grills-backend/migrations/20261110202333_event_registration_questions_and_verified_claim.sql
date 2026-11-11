-- Reuse events.registration_fields and ticket.metadata; no new public tables.
DO $migration$
DECLARE definition text; original text;
BEGIN
 definition:=pg_get_functiondef('public.hg_organizer_event_draft(uuid,uuid,text,jsonb)'::regprocedure);original:=definition;
 IF position('image_url,organizer_id' IN definition)=0 OR position('image_url=p_data->>''image_url''' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected organizer draft definition';END IF;
 definition:=replace(definition,' SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;',
 ' PERFORM pg_advisory_xact_lock(hashtextextended(''event-draft:''||p_event::text,0)); SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;');
 definition:=replace(definition,'image_url,organizer_id','image_url,registration_fields,organizer_id');
 definition:=replace(definition,'p_data->>''image_url'',p_actor','p_data->>''image_url'',coalesce(p_data->''registration_fields'',''[]''::jsonb),p_actor');
 definition:=replace(definition,'''organizer-''||p_event',
 'trim(both ''-'' from left(regexp_replace(lower(p_data->>''title''),''[^a-z0-9]+'',''-'',''g''),54))||''-''||left(replace(p_event::text,''-'',''''),8)');
 definition:=replace(definition,'image_url=p_data->>''image_url'',review_status',
 'image_url=p_data->>''image_url'',registration_fields=coalesce(p_data->''registration_fields'',registration_fields),review_status');
 IF definition=original THEN RAISE EXCEPTION 'Organizer question migration did not change its target';END IF;
 EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_organizer_event_attendees(uuid,uuid,text,integer,integer)'::regprocedure);
 IF position('tier.name AS tier_name,t.status' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected organizer attendees definition';END IF;
 definition:=replace(definition,'tier.name AS tier_name,t.status',
 'coalesce(t.metadata->''registration_answers'',''{}''::jsonb) AS registration_answers,tier.name AS tier_name,t.status');
 EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_handle_new_auth_user()'::regprocedure);
 IF position('where et.guest_email = new.email' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected Auth guest ticket reconciliation';END IF;
 definition:=replace(definition,'where et.guest_email = new.email',
 'where et.guest_email = new.email AND new.email_confirmed_at IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.event_checkins checked WHERE checked.ticket_id=et.id)');
 EXECUTE definition;
END $migration$;

-- Old guest-ticket reconciliation trusted the editable profile email during
-- profile creation. Require confirmed Auth identity instead.
CREATE OR REPLACE FUNCTION public.hg_link_guest_tickets_to_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE verified_email text;
BEGIN
 SELECT lower(btrim(email)) INTO verified_email FROM auth.users WHERE id=NEW.id AND email_confirmed_at IS NOT NULL;
 IF verified_email IS NULL THEN RETURN NEW;END IF;
 UPDATE public.event_tickets t SET user_id=NEW.id,is_guest=false
 WHERE lower(btrim(t.guest_email::text))=verified_email AND t.is_guest AND t.user_id IS NULL
 AND t.status NOT IN('cancelled','canceled','expired')
 AND NOT EXISTS(SELECT 1 FROM public.event_checkins c WHERE c.ticket_id=t.id)
 AND NOT EXISTS(SELECT 1 FROM public.event_tickets owned WHERE owned.event_id=t.event_id AND owned.user_id=NEW.id AND owned.status NOT IN('cancelled','canceled','expired'));
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_link_guest_tickets_to_user() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_link_guest_tickets_to_user() TO service_role;

CREATE OR REPLACE FUNCTION public.hg_link_verified_event_tickets(p_actor uuid)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE verified_email text; t public.event_tickets%rowtype; linked integer:=0;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT lower(btrim(u.email)) INTO verified_email FROM auth.users u JOIN public.profiles p ON p.id=u.id WHERE u.id=p_actor AND u.email_confirmed_at IS NOT NULL AND p.is_active;
 IF verified_email IS NULL THEN RETURN 0;END IF;
 FOR t IN SELECT * FROM public.event_tickets WHERE user_id IS NULL AND is_guest AND lower(btrim(guest_email::text))=verified_email AND status NOT IN('cancelled','canceled','expired') ORDER BY event_id,id LIMIT 100 LOOP
  -- Match admission's event -> profile -> ticket lock order.
  PERFORM 1 FROM public.events WHERE id=t.event_id FOR UPDATE;
  PERFORM 1 FROM public.profiles WHERE id=p_actor FOR UPDATE;
  SELECT * INTO t FROM public.event_tickets WHERE id=t.id FOR UPDATE;
  IF NOT FOUND THEN CONTINUE;END IF;
  IF t.user_id IS NOT NULL OR NOT t.is_guest OR lower(btrim(t.guest_email::text)) IS DISTINCT FROM verified_email THEN CONTINUE;END IF;
  IF EXISTS(SELECT 1 FROM public.event_checkins WHERE ticket_id=t.id) OR EXISTS(SELECT 1 FROM public.event_tickets WHERE event_id=t.event_id AND user_id=p_actor AND status NOT IN('cancelled','canceled','expired')) THEN CONTINUE;END IF;
  UPDATE public.event_tickets SET user_id=p_actor,is_guest=false WHERE id=t.id;
  linked:=linked+1;
 END LOOP;
 RETURN linked;
END $$;
REVOKE ALL ON FUNCTION public.hg_link_verified_event_tickets(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_link_verified_event_tickets(uuid) TO service_role;

-- Existing public UUID links remain valid; only the old unexposed auto slug
-- format is replaced. Deliberately authored slugs are preserved.
UPDATE public.events SET slug=trim(both '-' from left(regexp_replace(lower(title),'[^a-z0-9]+','-','g'),54))||'-'||left(replace(id::text,'-',''),8)
WHERE slug='organizer-'||id::text;

-- A single indexed join replaces per-ticket identifier round-trips/truncation.
CREATE OR REPLACE FUNCTION public.hg_event_attendance_count(p_event uuid)
RETURNS bigint LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT count(*) FROM public.event_checkins c JOIN public.event_tickets t ON t.id=c.ticket_id
 WHERE t.event_id=p_event AND coalesce(auth.role(),'')='service_role';
$$;
REVOKE ALL ON FUNCTION public.hg_event_attendance_count(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_event_attendance_count(uuid) TO service_role;
