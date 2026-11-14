DO $migration$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_organizer_event_draft(uuid,uuid,text,jsonb)'::regprocedure);
 IF position('IF a.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=a.campus_id AND is_active)' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected draft creation scope';END IF;
 definition:=replace(definition,'DECLARE a public.profiles%rowtype;e public.events%rowtype;','DECLARE a public.profiles%rowtype;e public.events%rowtype;write_campus uuid;');
 definition:=replace(definition,'IF a.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=a.campus_id AND is_active) THEN','write_campus:=a.campus_id;IF a.role::text=''super_admin'' THEN write_campus:=nullif(p_data->>''campus_id'','''')::uuid;END IF; IF (a.role::text<>''super_admin'' AND write_campus IS NULL) OR (write_campus IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=write_campus AND is_active)) THEN');
 definition:=replace(definition,'p_actor,a.campus_id,false,''draft'',0,0)','p_actor,write_campus,false,''draft'',0,0)');
 EXECUTE definition;
END $migration$;
