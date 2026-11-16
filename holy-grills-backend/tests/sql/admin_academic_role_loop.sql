-- Real RLS and profile-copy triggers. Entire fixture transaction rolls back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[]; actor uuid; target uuid; ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();
 da uuid:=gen_random_uuid();db uuid:=gen_random_uuid();dg uuid:=gen_random_uuid();la uuid:=gen_random_uuid();lb uuid:=gen_random_uuid();lg uuid:=gen_random_uuid();n integer; label text:='audit-academic-'||gen_random_uuid();
BEGIN
 SELECT array_agg(id) INTO ids FROM(SELECT p.id FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 2) q;
 actor:=ids[1];target:=ids[2];IF target IS NULL THEN RAISE EXCEPTION 'isolated audit profiles required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Academic A',label||'-a'),(cb,'[AUDIT rollback] Academic B',label||'-b');
 UPDATE public.profiles SET role='admin',is_active=true,campus_id=ca WHERE id=actor;
 INSERT INTO public.departments(id,name,slug,faculty,campus_id) VALUES(da,label||'-a',label||'-a','School A',ca),(db,label||'-b',label||'-b','School B',cb),(dg,label||'-global',label||'-global','Global school',NULL);
 INSERT INTO public.academic_levels(id,name,value,rank,sort_order,campus_id) VALUES(la,'Audit Level A',label||'-a',0,0,ca),(lb,'Audit Level B',label||'-b',0,0,cb),(lg,'Audit Global Level',label||'-global',0,0,NULL);
 UPDATE public.profiles SET role='student',is_active=true,campus_id=ca,department_id=da,department=label||'-a',faculty='School A',academic_level=label||'-a' WHERE id=target;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.departments SET name=label||'-renamed',faculty='Renamed school' WHERE id=da;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'own department update refused'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=target AND department=label||'-renamed' AND faculty='Renamed school') THEN RAISE EXCEPTION 'department rename/faculty did not reach profile'; END IF;
 UPDATE public.academic_levels SET value=label||'-new',sort_order=0,rank=0 WHERE id=la;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=target AND academic_level=label||'-new') THEN RAISE EXCEPTION 'level rename did not reach profile'; END IF;
 UPDATE public.departments SET faculty='Forbidden' WHERE id IN(db,dg);GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'admin changed foreign/global department'; END IF;
 UPDATE public.academic_levels SET rank=999 WHERE id IN(lb,lg);GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'admin changed foreign/global level'; END IF;
 BEGIN
  INSERT INTO public.departments(name,slug,faculty,campus_id) VALUES(label||'-foreign-insert',label||'-foreign-insert','Forbidden',cb);
  RAISE EXCEPTION 'foreign department insert allowed';
 EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN
  UPDATE public.departments SET campus_id=cb WHERE id=da;
  RAISE EXCEPTION 'cross-campus move allowed';
 EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN
  INSERT INTO public.departments(name,slug,faculty,campus_id) VALUES(label||'-renamed',label||'-newslug','Renamed school',ca);
  RAISE EXCEPTION 'same-campus duplicate name allowed';
 EXCEPTION WHEN unique_violation THEN NULL;END;
 UPDATE public.departments SET is_active=false WHERE id=da;
 IF NOT EXISTS(SELECT 1 FROM public.departments WHERE id=da AND NOT is_active) THEN RAISE EXCEPTION 'admin cannot read deactivated own entry'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"anon"}',true);PERFORM set_config('role','anon',true);
 IF EXISTS(SELECT 1 FROM public.departments WHERE id=da) THEN RAISE EXCEPTION 'hidden department still public'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.departments SET is_active=true WHERE id=da;
 UPDATE public.academic_levels SET is_active=false WHERE id=la;
 UPDATE public.academic_levels SET is_active=true WHERE id=la;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='student' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.departments SET faculty='Student mutation' WHERE id=da;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student edited department'; END IF;
 UPDATE public.academic_levels SET rank=999 WHERE id=la;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student edited level'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='super_admin' WHERE id=actor;PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.departments SET faculty='Super admin school' WHERE id IN(db,dg);GET DIAGNOSTICS n=ROW_COUNT;IF n<>2 THEN RAISE EXCEPTION 'super admin lacks global/foreign department access'; END IF;
 UPDATE public.academic_levels SET rank=1 WHERE id IN(lb,lg);GET DIAGNOSTICS n=ROW_COUNT;IF n<>2 THEN RAISE EXCEPTION 'super admin lacks global/foreign level access'; END IF;
 PERFORM set_config('role','none',true);
END $audit$;
ROLLBACK;
SELECT 'Real academic configuration: own-campus updates, profile rename/faculty/level propagation, hidden/public/restore, student/foreign/global mutation denial, super-admin superset and duplicate refusal passed; fixtures rolled back' AS evidence;
