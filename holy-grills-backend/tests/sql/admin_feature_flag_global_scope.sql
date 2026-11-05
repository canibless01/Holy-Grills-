-- Global switch update with a coexisting legacy campus override; rollback only.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE actor uuid;ca uuid:=gen_random_uuid();marker text:='audit_flag_'||replace(gen_random_uuid()::text,'-','');n integer;
BEGIN
 SELECT p.id INTO actor FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'isolated audit profile required';END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Feature scope',marker);
 UPDATE public.profiles SET role='super_admin',campus_id=ca,is_active=true WHERE id=actor;
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id,updated_by) VALUES(marker,true,null,actor),(marker,true,ca,actor);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.feature_flags SET is_active=false WHERE feature_name=marker AND campus_id IS NULL;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'global super-admin update did not affect exactly one row';END IF;
 IF NOT EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name=marker AND campus_id=ca AND is_active=true) THEN RAISE EXCEPTION 'global edit changed campus override';END IF;
 IF (SELECT count(*) FROM public.feature_flags WHERE feature_name=marker AND campus_id IS NULL)<>1 THEN RAISE EXCEPTION 'global lookup ambiguous';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='admin' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.feature_flags SET is_active=true WHERE feature_name=marker AND campus_id IS NULL;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'campus admin changed global switch';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='student' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.feature_flags SET is_active=true WHERE feature_name=marker;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student changed a switch';END IF;
 PERFORM set_config('role','none',true);
END $audit$;
ROLLBACK;
SELECT 'PASS: actual global flag edit targets one row, preserves campus override; campus admin and student cannot edit; all fixtures rolled back' AS evidence;
