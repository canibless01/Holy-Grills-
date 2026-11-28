-- Explicit resends get their own durable request receipt. Never reset an old
-- provider-accepted or uncertain delivery to queued.
CREATE INDEX IF NOT EXISTS notification_event_ticket_email_ticket_idx ON public.notification_deliveries
 ((dispatch_payload->>'ticket_id'),created_at DESC) WHERE dispatch_payload->>'kind'='event_ticket_email';
CREATE OR REPLACE FUNCTION public.hg_resend_event_ticket(p_event uuid,p_ticket uuid,p_request uuid,p_actor uuid,p_email text,p_signed boolean,p_title text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE t public.event_tickets%rowtype;e public.events%rowtype;a public.profiles%rowtype;d public.notification_deliveries%rowtype;recipient text;recipient_name text;allowed boolean:=false;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_TICKET_RESEND_ACCESS' USING ERRCODE='42501';END IF;
 IF p_request IS NULL OR p_title IS NULL OR p_body IS NULL THEN RAISE EXCEPTION 'HG_TICKET_RESEND_INVALID';END IF;
 PERFORM 1 FROM public.events WHERE id=p_event FOR UPDATE;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 SELECT * INTO t FROM public.event_tickets WHERE id=p_ticket AND event_id=p_event FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_TICKET_RESEND_ACCESS' USING ERRCODE='42501';END IF;
 IF p_actor IS NOT NULL THEN
  SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active;
  IF FOUND THEN allowed:=t.user_id=a.id OR a.role::text='super_admin' OR (a.role::text='admin' AND e.campus_id IS NOT NULL AND e.campus_id=a.campus_id) OR (a.role::text='event_organizer' AND e.organizer_id=a.id);END IF;
 END IF;
 -- Signed proof is checked by the backend against this exact ticket and recipient.
 allowed:=allowed OR coalesce(p_signed,false) OR (t.user_id IS NULL AND nullif(lower(btrim(p_email)),'') IS NOT NULL AND lower(btrim(p_email))=lower(btrim(t.guest_email::text)));
 IF NOT coalesce(allowed,false) THEN RAISE EXCEPTION 'HG_TICKET_RESEND_ACCESS' USING ERRCODE='42501';END IF;
 IF t.status NOT IN('confirmed','checked_in') OR t.payment_status NOT IN('paid','not_required') OR NOT coalesce(e.is_published,false) OR e.metadata->>'lifecycle_status'='cancelled' OR e.ends_at<=now() OR t.qr_expires_at<=now() THEN RAISE EXCEPTION 'HG_TICKET_RESEND_INVALID';END IF;
 IF t.user_id IS NOT NULL THEN SELECT lower(btrim(email::text)),coalesce(nullif(full_name,''),nullif(nickname,''),'there') INTO recipient,recipient_name FROM public.profiles WHERE id=t.user_id AND is_active;
 ELSE recipient:=lower(btrim(t.guest_email::text));recipient_name:=coalesce(nullif(t.guest_name,''),'there');END IF;
 IF nullif(recipient,'') IS NULL THEN RAISE EXCEPTION 'HG_TICKET_RESEND_INVALID';END IF;
 SELECT * INTO d FROM public.notification_deliveries WHERE id=p_request;
 IF FOUND THEN
  IF d.dispatch_payload->>'kind' IS DISTINCT FROM 'event_ticket_email' OR d.dispatch_payload->>'ticket_id' IS DISTINCT FROM t.id::text OR d.dispatch_payload->>'event_id' IS DISTINCT FROM e.id::text OR d.dispatch_payload->>'resend_actor' IS DISTINCT FROM p_actor::text OR d.dispatch_payload->'notification'->>'email' IS DISTINCT FROM recipient OR NOT(d.dispatch_payload ? 'resend_actor') THEN RAISE EXCEPTION 'HG_TICKET_RESEND_CONFLICT';END IF;
  RETURN jsonb_build_object('delivery_id',d.id,'state',d.dispatch->>'state','replayed',true);
 END IF;
 IF EXISTS(SELECT 1 FROM public.notification_deliveries WHERE dispatch_payload->>'kind'='event_ticket_email' AND dispatch_payload->>'ticket_id'=t.id::text AND created_at>now()-interval '2 minutes') THEN RAISE EXCEPTION 'HG_TICKET_RESEND_COOLDOWN';END IF;
 INSERT INTO public.notification_deliveries(id,user_id,channel,status,campus_id,dispatch,dispatch_payload)
 VALUES(p_request,t.user_id,'email','queued',t.campus_id,jsonb_build_object('version',1,'state','queued','key',p_request,'attempts',0,'next_at',now(),'expires_at',now()+interval '24 hours'),
 jsonb_build_object('kind','event_ticket_email','ticket_id',t.id,'event_id',e.id,'resend_actor',p_actor,'notification',jsonb_build_object('user_id',t.user_id,'type','event_registered','title',p_title,'body',p_body,'email',recipient,'name',recipient_name,'metadata',jsonb_build_object('event_title',e.title,'event_date',e.starts_at,'event_location',e.location))));
 RETURN jsonb_build_object('delivery_id',p_request,'state','queued','replayed',false);
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'HG_TICKET_RESEND_CONFLICT';
END $$;
REVOKE ALL ON FUNCTION public.hg_resend_event_ticket(uuid,uuid,uuid,uuid,text,boolean,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_resend_event_ticket(uuid,uuid,uuid,uuid,text,boolean,text,text) TO service_role;
