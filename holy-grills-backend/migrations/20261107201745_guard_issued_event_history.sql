-- Enforce the existing API policy even through direct administrator Data API calls.
CREATE OR REPLACE FUNCTION public.hg_guard_issued_event_history()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF TG_TABLE_NAME='events' THEN
  IF EXISTS(SELECT 1 FROM public.event_tickets WHERE event_id=OLD.id) THEN
   RAISE EXCEPTION 'Event has issued tickets; unpublish it instead' USING ERRCODE='23514';
  END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM public.event_tickets WHERE tier_id=OLD.id) THEN
   RAISE EXCEPTION 'Ticket tier has issued tickets; deactivate it instead' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN OLD;
END $$;
REVOKE ALL ON FUNCTION public.hg_guard_issued_event_history() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_guard_issued_event_history() TO service_role;
DROP TRIGGER IF EXISTS trg_guard_issued_event_history ON public.events;
CREATE TRIGGER trg_guard_issued_event_history BEFORE DELETE ON public.events FOR EACH ROW EXECUTE FUNCTION public.hg_guard_issued_event_history();
DROP TRIGGER IF EXISTS trg_guard_issued_tier_history ON public.event_ticket_tiers;
CREATE TRIGGER trg_guard_issued_tier_history BEFORE DELETE ON public.event_ticket_tiers FOR EACH ROW EXECUTE FUNCTION public.hg_guard_issued_event_history();
