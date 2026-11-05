-- Real authenticated calendar writes and graduation eligibility consumer; rollback only.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[];actor uuid;student uuid;ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();sem uuid:=gen_random_uuid();gr uuid:=gen_random_uuid();foreign_period uuid:=gen_random_uuid();global_period uuid:=gen_random_uuid();
 marker text:='audit-calendar-'||gen_random_uuid();today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;r jsonb;n integer;
BEGIN
 SELECT array_agg(id) INTO ids FROM(SELECT p.id FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%'
 AND NOT EXISTS(SELECT 1 FROM public.hp_transactions h WHERE h.user_id=p.id AND h.reference_type='graduation') ORDER BY p.id LIMIT 2) q;
 actor:=ids[1];student:=ids[2];IF student IS NULL THEN RAISE EXCEPTION 'isolated actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Calendar A',marker||'-a'),(cb,'[AUDIT rollback] Calendar B',marker||'-b');
 UPDATE public.profiles SET role='admin',campus_id=ca,is_active=true WHERE id=actor;
 UPDATE public.profiles SET role='student',campus_id=ca,is_active=true,graduation_claimed=false,academic_level=marker WHERE id=student;
 INSERT INTO public.academic_levels(name,value,rank,campus_id) VALUES('Audit final year',marker,400,ca),('Audit Postgraduate',marker||'-pg',0,ca);
 INSERT INTO public.system_settings(key,value,is_public,campus_id) VALUES('graduation_min_level','400'::jsonb,false,ca);
 INSERT INTO public.orders(user_id,campus_id,status,payment_status,subtotal,total_amount,delivered_at) SELECT student,ca,'delivered','paid',100,100,now() FROM generate_series(1,3);
 UPDATE public.academic_calendar SET is_active=false WHERE campus_id IS NULL AND period_type='graduation';
 INSERT INTO public.academic_calendar(id,name,period_type,start_date,end_date,academic_year,campus_id,is_active) VALUES(foreign_period,marker||'-b','semester',today,today+30,'audit',cb,true),(global_period,marker||'-global','semester',today,today+30,'audit',NULL,true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 INSERT INTO public.academic_calendar(id,name,period_type,start_date,end_date,academic_year,campus_id,is_active,description)
 VALUES(sem,marker||'-semester','semester',today-1,today+30,'audit',ca,true,'Audit persisted details'),(gr,marker||'-graduation','graduation',today+1,today+2,'audit',ca,true,'Audit future graduation');
 BEGIN
  INSERT INTO public.academic_calendar(name,period_type,start_date,end_date,academic_year,campus_id) VALUES(marker||'-invalid','semester',today,today-1,'audit',ca);
  RAISE EXCEPTION 'reversed date range accepted';EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN
  INSERT INTO public.academic_calendar(name,period_type,start_date,end_date,academic_year,campus_id) VALUES(marker||'-semester','semester',today,today+1,'audit',ca);
  RAISE EXCEPTION 'duplicate period accepted';EXCEPTION WHEN unique_violation THEN NULL;END;
 UPDATE public.academic_calendar SET description='Forbidden' WHERE id IN(foreign_period,global_period);GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'campus admin edited foreign/global calendar'; END IF;
 UPDATE public.academic_calendar SET name=marker||'-edited',description='Edited details' WHERE id=sem;
 IF NOT EXISTS(SELECT 1 FROM public.academic_calendar WHERE id=sem AND name=marker||'-edited' AND description='Edited details') THEN RAISE EXCEPTION 'calendar fields did not persist'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 r:=public.hg_graduation_eligibility(student);IF coalesce((r->>'eligible')::boolean,false) OR r->>'reason'<>'period' THEN RAISE EXCEPTION 'semester or future graduation enabled claim: %',r; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.academic_calendar SET start_date=today,end_date=today WHERE id=gr;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 r:=public.hg_graduation_eligibility(student);IF NOT coalesce((r->>'eligible')::boolean,false) OR r->'period'->>'id'<>gr::text THEN RAISE EXCEPTION 'current inclusive campus graduation did not enable eligible student: %',r; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.academic_calendar SET is_active=false WHERE id=gr;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 r:=public.hg_graduation_eligibility(student);IF coalesce((r->>'eligible')::boolean,false) THEN RAISE EXCEPTION 'retired graduation still enabled claim'; END IF;
 UPDATE public.academic_calendar SET is_active=true WHERE id=gr;
 r:=public.hg_graduation_eligibility(student);IF NOT coalesce((r->>'eligible')::boolean,false) THEN RAISE EXCEPTION 'restored graduation did not enable claim'; END IF;
 UPDATE public.profiles SET academic_level=marker||'-pg' WHERE id=student;
 r:=public.hg_graduation_eligibility(student);IF r->>'reason'<>'level' THEN RAISE EXCEPTION 'non-year PG option accidentally qualified: %',r; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',student)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.academic_calendar SET description='Student mutation' WHERE id=sem;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'student edited calendar'; END IF;
 IF EXISTS(SELECT 1 FROM public.academic_calendar WHERE id=gr AND NOT is_active) THEN RAISE EXCEPTION 'unexpected stale period state'; END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE public.profiles SET role='super_admin' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.academic_calendar SET description='Super update' WHERE id IN(foreign_period,global_period);GET DIAGNOSTICS n=ROW_COUNT;IF n<>2 THEN RAISE EXCEPTION 'super admin lacks calendar superset'; END IF;
 PERFORM set_config('role','none',true);
END $audit$;
ROLLBACK;
SELECT 'Calendar real RLS/fields/date and duplicate refusal; semester versus future/current/retired/restored graduation, inclusive WAT dates, non-year PG refusal and super-admin superset passed; all fixtures rolled back' AS evidence;
