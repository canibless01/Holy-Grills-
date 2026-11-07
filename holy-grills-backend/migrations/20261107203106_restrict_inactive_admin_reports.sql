-- Retain existing report bodies/signatures/grants; inactive accounts must fail
-- through direct RPC just as they do through the authenticated HTTP API.
DO $migration$
DECLARE f regprocedure; definition text;
BEGIN
 FOREACH f IN ARRAY ARRAY['public.get_hp_program_report_summary(date)'::regprocedure,'public.get_pending_squad_hp_report(integer)'::regprocedure] LOOP
  definition:=pg_get_functiondef(f);
  IF position('from public.profiles where id = auth.uid();' IN definition)>0 THEN
   definition:=replace(definition,'from public.profiles where id = auth.uid();','from public.profiles where id = auth.uid() AND is_active IS TRUE;');
   definition:=replace(definition,'raise exception ''insufficient_privilege'';','raise exception ''insufficient_privilege'' USING ERRCODE=''42501'';');
   EXECUTE definition;
  ELSIF position('from public.profiles where id = auth.uid() AND is_active IS TRUE;' IN definition)=0 THEN
   RAISE EXCEPTION 'Unexpected report authorization body: %',f;
  END IF;
 END LOOP;
END $migration$;
