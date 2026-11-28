BEGIN;
DO $$
DECLARE c uuid := gen_random_uuid(); d uuid:=gen_random_uuid(); l uuid:=gen_random_uuid(); snapshot jsonb;
BEGIN
  IF has_function_privilege('anon','public.hg_registration_options(uuid)','EXECUTE')
     OR has_function_privilege('authenticated','public.hg_registration_options(uuid)','EXECUTE') THEN
    RAISE EXCEPTION 'Reference RPC must remain service-only';
  END IF;
  INSERT INTO public.campuses(id,name,slug,is_active) VALUES(c,'Rollback reference fixture',c::text,true);
  INSERT INTO public.departments(id,name,slug,faculty,is_active,campus_id) VALUES
    (d,'Medicine and Surgery (MBBS)',d::text,'Fixture faculty',true,c);
  INSERT INTO public.academic_levels(id,name,value,is_active,campus_id) VALUES(l,'Fixture level','300',true,c);
  snapshot:=public.hg_registration_options(c);
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'departments') r WHERE r->>'id'=d::text)
    OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'levels') r WHERE r->>'id'=l::text)
    OR (SELECT count(*) FROM jsonb_array_elements(snapshot->'levels') r WHERE r->>'value'='300')<>1 THEN
    RAISE EXCEPTION 'Campus-specific references must be present and override shared rows';
  END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'departments') r WHERE r->>'campus_id' IS NOT NULL AND r->>'campus_id'<>c::text) THEN
    RAISE EXCEPTION 'Foreign campus references leaked';
  END IF;
  UPDATE public.campuses SET is_active=false WHERE id=c;
  IF public.hg_registration_options(c)->>'error'<>'campus_unavailable' THEN RAISE EXCEPTION 'Inactive campus accepted'; END IF;
END $$;
ROLLBACK;
