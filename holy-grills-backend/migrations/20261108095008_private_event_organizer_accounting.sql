
CREATE TABLE hg_internal.event_organizer_terms(
 tier_id uuid PRIMARY KEY REFERENCES public.event_ticket_tiers(id) ON DELETE CASCADE,
 event_id uuid NOT NULL REFERENCES public.events(id) ON DELETE CASCADE,
 organizer_amount numeric(14,2) NOT NULL CHECK(organizer_amount>=0 AND organizer_amount<1000000000),
 updated_by uuid REFERENCES public.profiles(id),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE hg_internal.event_ticket_earnings(
 ticket_id uuid PRIMARY KEY REFERENCES public.event_tickets(id),event_id uuid NOT NULL REFERENCES public.events(id),organizer_id uuid NOT NULL REFERENCES public.profiles(id),
 organizer_amount numeric(14,2) NOT NULL CHECK(organizer_amount>=0 AND organizer_amount<1000000000),created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE hg_internal.event_organizer_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.event_ticket_earnings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.event_organizer_terms,hg_internal.event_ticket_earnings FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.event_organizer_terms TO service_role;
GRANT SELECT,INSERT ON hg_internal.event_ticket_earnings TO service_role;
CREATE POLICY event_terms_service ON hg_internal.event_organizer_terms TO service_role USING(true) WITH CHECK(true);
CREATE POLICY event_earnings_service ON hg_internal.event_ticket_earnings TO service_role USING(true) WITH CHECK(true);
CREATE INDEX event_ticket_earnings_owner_event_idx ON hg_internal.event_ticket_earnings(event_id,organizer_id);
INSERT INTO hg_internal.event_organizer_terms(tier_id,event_id,organizer_amount) SELECT id,event_id,organizer_amount FROM public.event_ticket_tiers WHERE organizer_amount IS NOT NULL;
INSERT INTO hg_internal.event_ticket_earnings(ticket_id,event_id,organizer_id,organizer_amount) SELECT id,event_id,organizer_id_snapshot,organizer_amount_snapshot FROM public.event_tickets WHERE organizer_id_snapshot IS NOT NULL AND organizer_amount_snapshot>0;

DROP TRIGGER trg_event_organizer_snapshot ON public.event_tickets;
CREATE OR REPLACE FUNCTION public.hg_snapshot_event_organizer()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE owner_id uuid;amount numeric;
BEGIN
 SELECT organizer_id INTO owner_id FROM public.events WHERE id=NEW.event_id;
 SELECT organizer_amount INTO amount FROM hg_internal.event_organizer_terms WHERE tier_id=NEW.tier_id AND event_id=NEW.event_id;
 IF owner_id IS NOT NULL AND amount IS NOT NULL THEN
  INSERT INTO hg_internal.event_ticket_earnings(ticket_id,event_id,organizer_id,organizer_amount) VALUES(NEW.id,NEW.event_id,owner_id,amount);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_event_organizer_snapshot AFTER INSERT ON public.event_tickets FOR EACH ROW EXECUTE FUNCTION public.hg_snapshot_event_organizer();
CREATE OR REPLACE FUNCTION public.hg_keep_event_earnings_immutable()
RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
BEGIN RAISE EXCEPTION 'HG_ORGANIZER_SNAPSHOT_IMMUTABLE' USING ERRCODE='42501';END $$;
REVOKE ALL ON FUNCTION public.hg_keep_event_earnings_immutable() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_keep_event_earnings_immutable() TO service_role;
CREATE TRIGGER trg_immutable_event_earnings BEFORE UPDATE OR DELETE ON hg_internal.event_ticket_earnings FOR EACH ROW EXECUTE FUNCTION public.hg_keep_event_earnings_immutable();

DO $migration$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_review_organizer_event(uuid,uuid,text,jsonb)'::regprocedure);
 IF position('UPDATE public.event_ticket_tiers SET organizer_amount=amount' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected organizer terms writer';END IF;
 definition:=replace(definition,'UPDATE public.event_ticket_tiers SET organizer_amount=amount WHERE id=(item->>''id'')::uuid AND event_id=p_event;','PERFORM 1 FROM public.event_ticket_tiers WHERE id=(item->>''id'')::uuid AND event_id=p_event;');
 definition:=replace(definition,'IF NOT FOUND THEN RAISE EXCEPTION ''HG_ORGANIZER_INVALID'' USING ERRCODE=''23514'';END IF;', 'IF NOT FOUND THEN RAISE EXCEPTION ''HG_ORGANIZER_INVALID'' USING ERRCODE=''23514'';END IF; INSERT INTO hg_internal.event_organizer_terms(tier_id,event_id,organizer_amount,updated_by) VALUES((item->>''id'')::uuid,p_event,amount,p_actor) ON CONFLICT(tier_id) DO UPDATE SET organizer_amount=EXCLUDED.organizer_amount,updated_by=EXCLUDED.updated_by,updated_at=now();');
 definition:=replace(definition,'SELECT 1 FROM public.event_ticket_tiers WHERE event_id=e.id AND is_active AND organizer_amount IS NULL','SELECT 1 FROM public.event_ticket_tiers tier LEFT JOIN hg_internal.event_organizer_terms term ON term.tier_id=tier.id WHERE tier.event_id=e.id AND tier.is_active AND term.organizer_amount IS NULL');
 EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_organizer_event_balance(uuid,uuid)'::regprocedure);
 IF position('sum(organizer_amount_snapshot)' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected organizer earnings reader';END IF;
 definition:=replace(definition,'SELECT coalesce(sum(organizer_amount_snapshot),0) INTO earned FROM public.event_tickets WHERE event_id=p_event AND organizer_id_snapshot=e.organizer_id AND status=''confirmed'' AND payment_status IN(''paid'',''not_required'');','SELECT coalesce(sum(earned_ticket.organizer_amount),0) INTO earned FROM public.event_tickets ticket JOIN hg_internal.event_ticket_earnings earned_ticket ON earned_ticket.ticket_id=ticket.id WHERE ticket.event_id=p_event AND earned_ticket.organizer_id=e.organizer_id AND ticket.status=''confirmed'' AND ticket.payment_status IN(''paid'',''not_required'');');
 definition:=replace(definition,'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.price_naira,t.id),''[]'') INTO tiers FROM public.event_ticket_tiers t WHERE t.event_id=p_event;','SELECT coalesce(jsonb_agg(to_jsonb(t)||jsonb_build_object(''organizer_amount'',term.organizer_amount) ORDER BY t.price_naira,t.id),''[]'') INTO tiers FROM public.event_ticket_tiers t LEFT JOIN hg_internal.event_organizer_terms term ON term.tier_id=t.id WHERE t.event_id=p_event;');
 EXECUTE definition;
END $migration$;
ALTER TABLE public.event_ticket_tiers DROP COLUMN organizer_amount;
ALTER TABLE public.event_tickets DROP COLUMN organizer_id_snapshot,DROP COLUMN organizer_amount_snapshot;
ALTER POLICY event_tiers_organizer_read ON public.event_ticket_tiers USING(EXISTS(SELECT 1 FROM public.events e JOIN public.profiles p ON p.id=e.organizer_id WHERE e.id=event_id AND e.organizer_id=(SELECT auth.uid()) AND p.is_active AND p.role::text='event_organizer'));
