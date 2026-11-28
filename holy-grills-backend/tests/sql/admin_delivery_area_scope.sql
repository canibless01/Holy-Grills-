-- Actual centre/radius backing rows and settings RLS. All fixtures roll back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[];actor uuid;student uuid;ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();marker text:='audit-area-'||gen_random_uuid();n integer;
BEGIN
 SELECT array_agg(id) INTO ids FROM(SELECT p.id FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 2) q;
 actor:=ids[1];student:=ids[2];IF student IS NULL THEN RAISE EXCEPTION 'isolated audit profiles required'; END IF;
 INSERT INTO public.campuses(id,name,slug,lat,lon) VALUES(ca,'[AUDIT rollback] Area A',marker||'-a',7.30,5.14),(cb,'[AUDIT rollback] Area B',marker||'-b',6.50,3.40);
 UPDATE public.profiles SET role='admin',campus_id=ca,is_active=true WHERE id=actor;
 UPDATE public.profiles SET role='student',campus_id=ca,is_active=true WHERE id=student;
 INSERT INTO public.kitchen_settings(key,value,campus_id,updated_by) VALUES('max_delivery_radius_km','20',cb,actor);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 INSERT INTO public.kitchen_settings(key,value,campus_id,updated_by) VALUES('max_delivery_radius_km','1.5',ca,actor);
 UPDATE public.kitchen_settings SET value='2.5' WHERE key='max_delivery_radius_km' AND campus_id=ca;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'own radius save refused'; END IF;
 UPDATE public.kitchen_settings SET value='0.1' WHERE key='max_delivery_radius_km' AND campus_id=cb;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'campus admin changed foreign radius'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 -- Campus location routes use their authorized service write, not a new client RLS grant.
 UPDATE public.campuses SET lat=7.31,lon=5.15 WHERE id=ca;
 IF NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=cb AND lat=6.50 AND lon=3.40) OR NOT EXISTS(SELECT 1 FROM public.kitchen_settings WHERE key='max_delivery_radius_km' AND campus_id=cb AND value='20') THEN RAISE EXCEPTION 'other campus configuration changed'; END IF;
 UPDATE public.campuses SET lat=NULL,lon=NULL WHERE id=ca;
 IF NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=ca AND lat IS NULL AND lon IS NULL) OR NOT EXISTS(SELECT 1 FROM public.kitchen_settings WHERE key='max_delivery_radius_km' AND campus_id=ca AND value='2.5') THEN RAISE EXCEPTION 'clear centre changed radius'; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',student)::text,true);PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.kitchen_settings WHERE campus_id=ca) THEN RAISE EXCEPTION 'private kitchen settings exposed to student'; END IF;
 UPDATE public.kitchen_settings SET value='999' WHERE campus_id=ca;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student changed radius'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='super_admin' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.kitchen_settings SET value='10' WHERE key='max_delivery_radius_km' AND campus_id=cb;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'super admin cannot manage selected foreign radius'; END IF;
 PERFORM set_config('role','none',true);
END $audit$;
ROLLBACK;
SELECT 'Delivery area real rows: scoped centre/radius save and clear, other-campus preservation, private settings, campus/student refusal and super-admin superset passed; all fixtures rolled back' AS evidence;
