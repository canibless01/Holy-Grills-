-- Preserve the live functions (including unrelated integration changes) and add
-- one admission guard under their existing event-row locks. No ledger changes.
DO $migration$
DECLARE
  target regprocedure;
  definition text;
  marker text := '  IF p_tier_id IS NOT NULL THEN';
  guard text := E'  IF p_tier_id IS NULL AND EXISTS (SELECT 1 FROM public.event_ticket_tiers WHERE event_id = p_event_id) THEN\n    RAISE EXCEPTION USING MESSAGE = ''Ticket tier required'', ERRCODE = ''P0001'';\n  END IF;\n\n';
BEGIN
  FOREACH target IN ARRAY ARRAY[
    'public.register_for_event_paid(uuid,uuid,uuid,boolean,numeric,uuid,jsonb)'::regprocedure,
    'public.register_for_event_guest_paid(uuid,citext,text,text,uuid,uuid,jsonb)'::regprocedure
  ] LOOP
    definition := pg_get_functiondef(target);
    IF position('Ticket tier required' IN definition) > 0 THEN CONTINUE; END IF;
    IF position(marker IN definition) = 0 THEN
      RAISE EXCEPTION 'Admission function changed; review before applying: %', target;
    END IF;
    EXECUTE replace(definition, marker, guard || marker);
  END LOOP;
END
$migration$;
