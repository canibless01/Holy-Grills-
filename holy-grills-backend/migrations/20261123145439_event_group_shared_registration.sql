-- Preserve existing group helper identity/grants; annotate shared purchaser answers.
DO $migration$
DECLARE body text; before_text text; after_text text;
BEGIN
 SELECT pg_get_functiondef('public.hg_create_event_group(uuid,uuid,jsonb,jsonb,text,numeric,uuid,text,text)'::regprocedure) INTO body;
 before_text:=$old$jsonb_build_object('registration_answers',coalesce(a->'answers','{}'::jsonb))$old$;
 after_text:=$new$jsonb_build_object('registration_answers',coalesce(a->'answers','{}'::jsonb)) || CASE WHEN jsonb_typeof(a->'registration_context')='object' THEN jsonb_build_object('registration_context',a->'registration_context') ELSE '{}'::jsonb END$new$;
 IF strpos(body,after_text)=0 THEN
  IF strpos(body,before_text)=0 THEN RAISE EXCEPTION 'Unexpected group registration definition';END IF;
  EXECUTE replace(body,before_text,after_text);
 END IF;
END $migration$;
NOTIFY pgrst,'reload schema';
