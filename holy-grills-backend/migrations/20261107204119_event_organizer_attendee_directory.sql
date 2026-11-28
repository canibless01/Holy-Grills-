CREATE OR REPLACE FUNCTION public.hg_organizer_event_attendees(p_actor uuid,p_event uuid,p_search text DEFAULT '',p_limit integer DEFAULT 50,p_offset integer DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;rows jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('event_organizer','admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF NOT ((a.role::text='event_organizer' AND e.organizer_id=p_actor) OR a.role::text='super_admin' OR (a.role::text='admin' AND e.campus_id=a.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_limit NOT BETWEEN 1 AND 500 OR p_offset<0 OR length(coalesce(p_search,''))>160 THEN RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.registered_at,r.ticket_id),'[]') INTO rows FROM(
  SELECT t.id AS ticket_id,coalesce(p.full_name,t.guest_name) AS full_name,coalesce(p.email,t.guest_email::text) AS email,coalesce(p.phone,t.guest_phone) AS phone,
   tier.name AS tier_name,t.status,t.payment_status,t.created_at AS registered_at,(ci.id IS NOT NULL) AS checked_in,ci.created_at AS checked_in_at
  FROM public.event_tickets t LEFT JOIN public.profiles p ON p.id=t.user_id LEFT JOIN public.event_ticket_tiers tier ON tier.id=t.tier_id LEFT JOIN public.event_checkins ci ON ci.ticket_id=t.id
  WHERE t.event_id=p_event AND (coalesce(p_search,'')='' OR position(lower(trim(p_search)) IN lower(concat_ws(' ',t.id::text,p.full_name,t.guest_name,p.email,t.guest_email::text,p.phone,t.guest_phone)))>0)
  ORDER BY t.created_at,t.id LIMIT p_limit OFFSET p_offset
 ) r;
 RETURN rows;
END $$;
REVOKE ALL ON FUNCTION public.hg_organizer_event_attendees(uuid,uuid,text,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_organizer_event_attendees(uuid,uuid,text,integer,integer) TO service_role;
