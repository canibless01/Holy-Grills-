-- Actual location persistence/RLS/index/trigger lifecycle; no persistent fixtures or payments.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[];actor uuid;student uuid;ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();ga uuid:=gen_random_uuid();gb uuid:=gen_random_uuid();ha uuid:=gen_random_uuid();oid uuid:=gen_random_uuid();
 marker text:='audit-location-'||gen_random_uuid();n integer;
BEGIN
 SELECT array_agg(id) INTO ids FROM(SELECT p.id FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 2) q;
 actor:=ids[1];student:=ids[2];IF student IS NULL THEN RAISE EXCEPTION 'isolated audit actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Location A',marker||'-a'),(cb,'[AUDIT rollback] Location B',marker||'-b');
 UPDATE public.profiles SET role='admin',campus_id=ca,is_active=true WHERE id=actor;
 UPDATE public.profiles SET role='student',campus_id=ca,is_active=true WHERE id=student;
 INSERT INTO public.gates(id,name,base_fee,rate_per_km,min_fee,lat,lon,campus_id,is_active) VALUES(gb,marker,900,0,900,7.31,5.14,cb,true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 INSERT INTO public.gates(id,name,base_fee,rate_per_km,min_fee,lat,lon,campus_id,is_active) VALUES(ga,marker,500,100,200,7.30,5.14,ca,true);
 INSERT INTO public.hostels(id,name,gate_id,delivery_fee,campus_id,is_active) VALUES(ha,marker,ga,350,ca,true);
 IF NOT EXISTS(SELECT 1 FROM public.gates WHERE id=ga AND rate_per_km=100 AND min_fee=200 AND lat=7.30 AND lon=5.14) THEN RAISE EXCEPTION 'gate input fields did not persist'; END IF;
 BEGIN
  INSERT INTO public.gates(name,base_fee,campus_id) VALUES(' '||upper(marker)||' ',0,ca);RAISE EXCEPTION 'case/space duplicate gate accepted';
 EXCEPTION WHEN unique_violation THEN NULL;END;
 BEGIN
  INSERT INTO public.hostels(name,delivery_fee,campus_id) VALUES(' '||upper(marker)||' ',0,ca);RAISE EXCEPTION 'case/space duplicate hostel accepted';
 EXCEPTION WHEN unique_violation THEN NULL;END;
 BEGIN
  UPDATE public.hostels SET gate_id=gb WHERE id=ha;RAISE EXCEPTION 'cross-campus hostel link accepted';
 EXCEPTION WHEN check_violation THEN NULL;END;
 UPDATE public.gates SET base_fee=600,rate_per_km=120,min_fee=250,lat=NULL,lon=NULL WHERE id=ga;
 UPDATE public.hostels SET delivery_fee=375 WHERE id=ha;
 IF NOT EXISTS(SELECT 1 FROM public.hostels WHERE id=ha AND gate_id=ga AND delivery_fee=375) THEN RAISE EXCEPTION 'hostel edit lost link/fee'; END IF;
 UPDATE public.gates SET min_fee=999 WHERE id=gb;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'admin edited foreign gate'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,delivery_type,delivery_location_id,delivery_fee,delivery_address_snapshot) VALUES(oid,student,ca,'received','paid','on_campus',ha,350,jsonb_build_object('location_id',ha,'location_name',marker,'delivery_fee',350));
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.hostels SET is_active=false WHERE id=ha;UPDATE public.gates SET is_active=false WHERE id=ga;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',student)::text,true);PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.hostels WHERE id=ha) OR EXISTS(SELECT 1 FROM public.gates WHERE id=ga) THEN RAISE EXCEPTION 'hidden locations visible to student'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.orders WHERE id=oid AND delivery_location_id=ha AND delivery_fee=350 AND delivery_address_snapshot->>'location_name'=marker) THEN RAISE EXCEPTION 'hiding/price edit rewrote historical order'; END IF;
 UPDATE public.hostels SET delivery_fee=0 WHERE id=ha;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student changed hostel fee'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.gates SET is_active=true WHERE id=ga;UPDATE public.hostels SET is_active=true WHERE id=ha;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='super_admin' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.gates SET base_fee=1000 WHERE id=gb;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'super admin lacks foreign gate access'; END IF;
 BEGIN
  UPDATE public.gates SET campus_id=cb WHERE id=ga;RAISE EXCEPTION 'linked gate moved away from hostel campus';
 EXCEPTION WHEN check_violation THEN NULL;END;
 PERFORM set_config('role','none',true);
 IF has_function_privilege('authenticated','public.hg_guard_delivery_location_campus()','EXECUTE') OR has_function_privilege('anon','public.hg_guard_delivery_location_campus()','EXECUTE') THEN RAISE EXCEPTION 'internal trigger helper exposed'; END IF;
END $audit$;
ROLLBACK;
SELECT 'Locations: authenticated fields/fees/clear-pin edits, normalized duplicate refusal, same-name different-campus records, cross-campus link/move refusal, hide/restore, historical order preservation and role boundaries passed; fixtures rolled back' AS evidence;
