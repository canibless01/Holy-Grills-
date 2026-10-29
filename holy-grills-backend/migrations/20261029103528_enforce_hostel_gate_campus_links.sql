-- Reuse existing gates/hostels and enforce their existing campus boundary.
LOCK TABLE public.gates, public.hostels IN SHARE ROW EXCLUSIVE MODE;
DO $verify$
BEGIN
 IF EXISTS(SELECT 1 FROM public.hostels h JOIN public.gates g ON g.id=h.gate_id WHERE h.campus_id IS DISTINCT FROM g.campus_id)
 THEN RAISE EXCEPTION 'existing_hostel_gate_scope_requires_review'; END IF;
END $verify$;
CREATE OR REPLACE FUNCTION public.hg_guard_delivery_location_campus()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $function$
DECLARE gate_campus uuid;
BEGIN
 IF TG_TABLE_NAME='hostels' THEN
  IF NEW.gate_id IS NULL THEN RETURN NEW; END IF;
  -- SHARE prevents a concurrent gate campus move until this link commits.
  SELECT campus_id INTO gate_campus FROM public.gates WHERE id=NEW.gate_id FOR SHARE;
  IF NOT FOUND OR gate_campus IS DISTINCT FROM NEW.campus_id THEN
   RAISE EXCEPTION 'hostel_gate_scope_mismatch' USING ERRCODE='23514';
  END IF;
 ELSE
  IF NEW.campus_id IS DISTINCT FROM OLD.campus_id AND EXISTS(
   SELECT 1 FROM public.hostels WHERE gate_id=OLD.id AND campus_id IS DISTINCT FROM NEW.campus_id)
  THEN RAISE EXCEPTION 'linked_gate_scope_change_refused' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $function$;
REVOKE ALL ON FUNCTION public.hg_guard_delivery_location_campus() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_guard_delivery_location_campus() TO service_role;
CREATE TRIGGER hostels_guard_gate_campus BEFORE INSERT OR UPDATE OF gate_id,campus_id ON public.hostels
 FOR EACH ROW EXECUTE FUNCTION public.hg_guard_delivery_location_campus();
CREATE TRIGGER gates_guard_linked_campus BEFORE UPDATE OF campus_id ON public.gates
 FOR EACH ROW EXECUTE FUNCTION public.hg_guard_delivery_location_campus();
