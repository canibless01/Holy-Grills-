ALTER TABLE public.events ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'approved' CHECK(review_status IN('draft','submitted','changes_requested','approved'));
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS review_notes text;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS reviewed_by uuid REFERENCES public.profiles(id);
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS submitted_at timestamptz;
ALTER TABLE public.events ADD CONSTRAINT event_publication_requires_review CHECK(NOT is_published OR review_status='approved');
ALTER TABLE public.event_ticket_tiers ADD COLUMN IF NOT EXISTS organizer_amount numeric(14,2) CHECK(organizer_amount>=0 AND organizer_amount<1000000000);
ALTER TABLE public.event_tickets ADD COLUMN IF NOT EXISTS organizer_id_snapshot uuid REFERENCES public.profiles(id);
ALTER TABLE public.event_tickets ADD COLUMN IF NOT EXISTS organizer_amount_snapshot numeric(14,2) NOT NULL DEFAULT 0 CHECK(organizer_amount_snapshot>=0 AND organizer_amount_snapshot<1000000000);

CREATE TABLE hg_internal.event_payout_requests(
 id uuid PRIMARY KEY, event_id uuid NOT NULL REFERENCES public.events(id), organizer_id uuid NOT NULL REFERENCES public.profiles(id),
 amount numeric(14,2) NOT NULL CHECK(amount>0 AND amount<1000000000),
 state text NOT NULL DEFAULT 'pending' CHECK(state IN('pending','approved','paid','rejected','cancelled')),
 bank_details jsonb NOT NULL, bank_transfer_reference text UNIQUE, admin_notes text,
 reviewed_by uuid REFERENCES public.profiles(id), created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),paid_at timestamptz
);
ALTER TABLE hg_internal.event_payout_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.event_payout_requests FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA hg_internal TO service_role;
GRANT SELECT,INSERT,UPDATE ON hg_internal.event_payout_requests TO service_role;
CREATE POLICY event_payouts_service ON hg_internal.event_payout_requests TO service_role USING(true) WITH CHECK(true);
CREATE INDEX event_payouts_event_state_idx ON hg_internal.event_payout_requests(event_id,state);
CREATE INDEX events_organizer_idx ON public.events(organizer_id,created_at DESC);

-- Capture the agreed amount when the seat/price is reserved; later pricing edits
-- cannot rewrite the organizer's earned contract. Older tickets stay at zero.
CREATE OR REPLACE FUNCTION public.hg_snapshot_event_organizer()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE owner_id uuid; amount numeric;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF NEW.organizer_id_snapshot IS DISTINCT FROM OLD.organizer_id_snapshot OR NEW.organizer_amount_snapshot IS DISTINCT FROM OLD.organizer_amount_snapshot THEN
   RAISE EXCEPTION 'HG_ORGANIZER_SNAPSHOT_IMMUTABLE' USING ERRCODE='42501';
  END IF;
  RETURN NEW;
 END IF;
 SELECT organizer_id INTO owner_id FROM public.events WHERE id=NEW.event_id;
 SELECT organizer_amount INTO amount FROM public.event_ticket_tiers WHERE id=NEW.tier_id AND event_id=NEW.event_id;
 NEW.organizer_id_snapshot:=owner_id;
 NEW.organizer_amount_snapshot:=coalesce(amount,0);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_snapshot_event_organizer() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_snapshot_event_organizer() TO service_role;
CREATE TRIGGER trg_event_organizer_snapshot BEFORE INSERT OR UPDATE ON public.event_tickets FOR EACH ROW EXECUTE FUNCTION public.hg_snapshot_event_organizer();

CREATE OR REPLACE FUNCTION public.hg_guard_event_organizer_owner()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NEW.organizer_id IS DISTINCT FROM OLD.organizer_id AND EXISTS(SELECT 1 FROM public.event_tickets WHERE event_id=OLD.id) THEN
  RAISE EXCEPTION 'HG_ORGANIZER_OWNER_HAS_TICKETS' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.hg_guard_event_organizer_owner() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_guard_event_organizer_owner() TO service_role;
CREATE TRIGGER trg_event_organizer_owner BEFORE UPDATE ON public.events FOR EACH ROW EXECUTE FUNCTION public.hg_guard_event_organizer_owner();

CREATE POLICY events_organizer_read ON public.events FOR SELECT TO authenticated
 USING(organizer_id=(SELECT auth.uid()) AND EXISTS(SELECT 1 FROM public.profiles WHERE id=(SELECT auth.uid()) AND role::text='event_organizer' AND is_active));
CREATE POLICY event_tiers_organizer_read ON public.event_ticket_tiers FOR SELECT TO authenticated
 USING(EXISTS(SELECT 1 FROM public.events e WHERE e.id=event_id AND e.organizer_id=(SELECT auth.uid())));
-- No organizer INSERT/UPDATE/DELETE policy is added. Draft/review writes are service-only.

CREATE OR REPLACE FUNCTION public.hg_organizer_event_draft(p_actor uuid,p_event uuid,p_action text,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('event_organizer','admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;
 IF NOT FOUND AND p_action='create' THEN
  IF a.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=a.campus_id AND is_active) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
  INSERT INTO public.events(id,title,slug,description,location,starts_at,ends_at,capacity,max_attendees,image_url,organizer_id,campus_id,is_published,review_status,hp_reward,hp_per_attendee)
  VALUES(p_event,p_data->>'title','organizer-'||p_event,p_data->>'description',p_data->>'location',(p_data->>'starts_at')::timestamptz,(p_data->>'ends_at')::timestamptz,(p_data->>'capacity')::integer,(p_data->>'capacity')::integer,p_data->>'image_url',p_actor,a.campus_id,false,'draft',0,0) RETURNING * INTO e;
  RETURN to_jsonb(e);
 END IF;
 IF e.id IS NULL THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF NOT ((a.role::text='event_organizer' AND e.organizer_id=p_actor) OR a.role::text='super_admin' OR (a.role::text='admin' AND e.campus_id=a.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_action='create' THEN
  IF e.organizer_id<>p_actor OR e.title IS DISTINCT FROM p_data->>'title' OR e.location IS DISTINCT FROM p_data->>'location' OR e.starts_at IS DISTINCT FROM (p_data->>'starts_at')::timestamptz THEN RAISE EXCEPTION 'HG_ORGANIZER_CONFLICT' USING ERRCODE='23505';END IF;
  RETURN to_jsonb(e);
 END IF;
 IF p_action='submit' AND e.review_status='submitted' THEN RETURN to_jsonb(e);END IF;
 IF e.review_status NOT IN('draft','changes_requested') THEN RAISE EXCEPTION 'HG_ORGANIZER_REVIEW_LOCKED' USING ERRCODE='23514';END IF;
 IF p_action='edit' THEN
  UPDATE public.events SET title=p_data->>'title',description=p_data->>'description',location=p_data->>'location',starts_at=(p_data->>'starts_at')::timestamptz,ends_at=(p_data->>'ends_at')::timestamptz,capacity=(p_data->>'capacity')::integer,max_attendees=(p_data->>'capacity')::integer,image_url=p_data->>'image_url',review_status='draft',is_published=false WHERE id=p_event RETURNING * INTO e;
 ELSIF p_action='submit' THEN
  IF e.starts_at<=now() OR e.ends_at<=e.starts_at THEN RAISE EXCEPTION 'HG_ORGANIZER_DATES' USING ERRCODE='23514';END IF;
  UPDATE public.events SET review_status='submitted',submitted_at=now(),is_published=false WHERE id=p_event RETURNING * INTO e;
 ELSE RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.hg_review_organizer_event(p_actor uuid,p_event uuid,p_action text,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;owner_id uuid;item jsonb;amount numeric;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF a.role::text<>'super_admin' AND (e.campus_id IS NULL OR e.campus_id IS DISTINCT FROM a.campus_id) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_action='configure' THEN
  owner_id:=(p_data->>'organizer_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=owner_id AND is_active AND role::text='event_organizer' AND (e.campus_id IS NULL OR campus_id=e.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_OWNER_INVALID' USING ERRCODE='23514';END IF;
  UPDATE public.events SET organizer_id=owner_id WHERE id=p_event;
  FOR item IN SELECT * FROM jsonb_array_elements(coalesce(p_data->'tiers','[]')) LOOP
   amount:=(item->>'organizer_amount')::numeric;
   IF amount IS NULL OR amount<0 OR amount>=1000000000 OR amount::text IN('NaN','Infinity','-Infinity') OR amount<>round(amount,2) THEN RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
   UPDATE public.event_ticket_tiers SET organizer_amount=amount WHERE id=(item->>'id')::uuid AND event_id=p_event;
   IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
  END LOOP;
 ELSIF p_action='approve' THEN
  IF e.organizer_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=e.organizer_id AND is_active AND role::text='event_organizer') THEN RAISE EXCEPTION 'HG_ORGANIZER_OWNER_INVALID' USING ERRCODE='23514';END IF;
  IF e.is_paid AND NOT EXISTS(SELECT 1 FROM public.event_ticket_tiers WHERE event_id=e.id AND is_active) THEN RAISE EXCEPTION 'HG_ORGANIZER_TERMS_REQUIRED' USING ERRCODE='23514';END IF;
  IF EXISTS(SELECT 1 FROM public.event_ticket_tiers WHERE event_id=e.id AND is_active AND organizer_amount IS NULL) THEN RAISE EXCEPTION 'HG_ORGANIZER_TERMS_REQUIRED' USING ERRCODE='23514';END IF;
  UPDATE public.events SET review_status='approved',is_published=true,review_notes=p_data->>'notes',reviewed_by=p_actor WHERE id=p_event;
 ELSIF p_action='changes_requested' THEN
  IF length(trim(coalesce(p_data->>'notes','')))<3 THEN RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
  UPDATE public.events SET review_status='changes_requested',is_published=false,review_notes=p_data->>'notes',reviewed_by=p_actor WHERE id=p_event;
 ELSE RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 RETURN to_jsonb(e);
END $$;

CREATE OR REPLACE FUNCTION public.hg_organizer_event_balance(p_actor uuid,p_event uuid)
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;earned numeric;paid numeric;reserved numeric;requests jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('event_organizer','admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF NOT ((a.role::text='event_organizer' AND e.organizer_id=p_actor) OR a.role::text='super_admin' OR (a.role::text='admin' AND e.campus_id=a.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT coalesce(sum(organizer_amount_snapshot),0) INTO earned FROM public.event_tickets WHERE event_id=p_event AND organizer_id_snapshot=e.organizer_id AND status='confirmed' AND payment_status IN('paid','not_required');
 SELECT coalesce(sum(amount) FILTER(WHERE state='paid'),0),coalesce(sum(amount) FILTER(WHERE state IN('pending','approved')),0),coalesce(jsonb_agg(to_jsonb(p) ORDER BY created_at DESC),'[]') INTO paid,reserved,requests FROM hg_internal.event_payout_requests p WHERE event_id=p_event AND organizer_id=e.organizer_id;
 RETURN jsonb_build_object('event',to_jsonb(e),'earned',earned,'paid',paid,'reserved',reserved,'available',greatest(0,earned-paid-reserved),'overpaid',greatest(0,paid-earned),'requests',requests);
END $$;

CREATE OR REPLACE FUNCTION public.hg_event_payout_action(p_actor uuid,p_event uuid,p_request uuid,p_action text,p_data jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;r hg_internal.event_payout_requests%rowtype;b jsonb;available numeric;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;
 b:=public.hg_organizer_event_balance(p_actor,p_event);
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active;
 SELECT * INTO r FROM hg_internal.event_payout_requests WHERE id=p_request FOR UPDATE;
 IF p_action='request' THEN
  IF e.organizer_id IS DISTINCT FROM p_actor THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
  IF r.id IS NOT NULL THEN
   IF r.event_id<>p_event OR r.organizer_id<>p_actor OR r.bank_details IS DISTINCT FROM p_data THEN RAISE EXCEPTION 'HG_ORGANIZER_CONFLICT' USING ERRCODE='23505';END IF;
   RETURN to_jsonb(r);
  END IF;
  available:=(b->>'available')::numeric;
  IF e.ends_at IS NULL OR e.ends_at>now() OR e.review_status<>'approved' THEN RAISE EXCEPTION 'HG_ORGANIZER_PAYOUT_NOT_DUE' USING ERRCODE='23514';END IF;
  IF available<=0 THEN RAISE EXCEPTION 'HG_ORGANIZER_NO_BALANCE' USING ERRCODE='23514';END IF;
  IF coalesce(p_data->>'account_number','') !~ '^[0-9]{10}$' OR length(trim(coalesce(p_data->>'bank_name','')))<2 OR length(trim(coalesce(p_data->>'account_name','')))<2 THEN RAISE EXCEPTION 'HG_ORGANIZER_BANK_INVALID' USING ERRCODE='23514';END IF;
  INSERT INTO hg_internal.event_payout_requests(id,event_id,organizer_id,amount,bank_details) VALUES(p_request,p_event,p_actor,available,p_data) RETURNING * INTO r;
  RETURN to_jsonb(r);
 END IF;
 IF r.id IS NULL OR r.event_id<>p_event THEN RAISE EXCEPTION 'HG_ORGANIZER_NOT_FOUND' USING ERRCODE='P0002';END IF;
 IF p_action='cancel' AND e.organizer_id=p_actor AND r.state='pending' THEN
  UPDATE hg_internal.event_payout_requests SET state='cancelled',updated_at=now() WHERE id=r.id RETURNING * INTO r;RETURN to_jsonb(r);
 END IF;
 IF a.role::text NOT IN('admin','super_admin') THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF r.state='paid' THEN
  IF p_action='paid' AND r.bank_transfer_reference=p_data->>'reference' THEN RETURN to_jsonb(r);END IF;
  RAISE EXCEPTION 'HG_ORGANIZER_CONFLICT' USING ERRCODE='23505';
 END IF;
 IF p_action='reject' AND r.state IN('pending','approved') THEN
  IF length(trim(coalesce(p_data->>'notes','')))<3 THEN RAISE EXCEPTION 'HG_ORGANIZER_INVALID' USING ERRCODE='23514';END IF;
  UPDATE hg_internal.event_payout_requests SET state='rejected',admin_notes=p_data->>'notes',reviewed_by=p_actor,updated_at=now() WHERE id=r.id RETURNING * INTO r;RETURN to_jsonb(r);
 END IF;
 IF p_action='approve' AND r.state='approved' THEN RETURN to_jsonb(r);END IF;
 IF NOT ((p_action='approve' AND r.state='pending') OR (p_action='paid' AND r.state='approved')) THEN RAISE EXCEPTION 'HG_ORGANIZER_CONFLICT' USING ERRCODE='23505';END IF;
 -- Refunds serialize on this event too. Recheck entitlement immediately before
 -- approval/recording transfer. Overpayments after a later refund remain visible.
 IF e.ends_at IS NULL OR e.ends_at>now() OR (b->>'earned')::numeric < (b->>'paid')::numeric+(b->>'reserved')::numeric THEN RAISE EXCEPTION 'HG_ORGANIZER_BALANCE_CHANGED' USING ERRCODE='23514';END IF;
 IF p_action='paid' AND length(trim(coalesce(p_data->>'reference','')))<4 THEN RAISE EXCEPTION 'HG_ORGANIZER_REFERENCE_REQUIRED' USING ERRCODE='23514';END IF;
 UPDATE hg_internal.event_payout_requests SET state=CASE WHEN p_action='paid' THEN 'paid' ELSE 'approved' END,reviewed_by=p_actor,admin_notes=p_data->>'notes',updated_at=now(),paid_at=CASE WHEN p_action='paid' THEN now() ELSE NULL END,bank_transfer_reference=CASE WHEN p_action='paid' THEN trim(p_data->>'reference') ELSE NULL END WHERE id=r.id RETURNING * INTO r;
 RETURN to_jsonb(r);
END $$;

REVOKE ALL ON FUNCTION public.hg_organizer_event_draft(uuid,uuid,text,jsonb),public.hg_review_organizer_event(uuid,uuid,text,jsonb),public.hg_organizer_event_balance(uuid,uuid),public.hg_event_payout_action(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_organizer_event_draft(uuid,uuid,text,jsonb),public.hg_review_organizer_event(uuid,uuid,text,jsonb),public.hg_organizer_event_balance(uuid,uuid),public.hg_event_payout_action(uuid,uuid,uuid,text,jsonb) TO service_role;

-- Campus admins may appoint/manage this subordinate role; other staff/admin
-- escalation restrictions and balance guards remain exactly as before.
DO $guard$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_protect_profile_columns()'::regprocedure);
 IF position('old.role in (''student'',''kitchen'',''rider'') and new.role in (''student'',''kitchen'',''rider'')' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected profile role guard';END IF;
 definition:=replace(definition,'old.role in (''student'',''kitchen'',''rider'') and new.role in (''student'',''kitchen'',''rider'')','old.role in (''student'',''kitchen'',''rider'',''event_organizer'') and new.role in (''student'',''kitchen'',''rider'',''event_organizer'')');EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)'::regprocedure);
 IF position('is_staff:=a.role::text IN (''admin'',''super_admin'');' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected event admission guard';END IF;
 definition:=replace(definition,'is_staff:=a.role::text IN (''admin'',''super_admin'');','is_staff:=a.role::text IN (''admin'',''super_admin'') OR (a.role::text=''event_organizer'' AND e.organizer_id=a.id);');
 definition:=replace(definition,'IF is_staff AND a.role::text<>''super_admin'' AND','IF is_staff AND a.role::text=''admin'' AND');EXECUTE definition;
END $guard$;
