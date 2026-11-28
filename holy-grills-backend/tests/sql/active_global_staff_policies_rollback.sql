BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();inactive uuid:=gen_random_uuid();admin uuid:=gen_random_uuid();student uuid:=gen_random_uuid();actor uuid;id uuid;target record;n integer;fixture jsonb:='{}';own_level uuid:=gen_random_uuid();foreign_level uuid:=gen_random_uuid();
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Global policies','audit-'||c),(other_c,'[AUDIT rollback] Foreign','audit-'||other_c);
 FOREACH actor IN ARRAY ARRAY[sa,inactive,admin,student] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-policy-'||actor||'@example.invalid','{}');
  UPDATE profiles SET campus_id=c,is_active=true,role='student' WHERE profiles.id=actor;
 END LOOP;
 UPDATE profiles SET role='super_admin' WHERE profiles.id IN(sa,inactive);
 UPDATE profiles SET is_active=false WHERE profiles.id=inactive;
 UPDATE profiles SET role='admin' WHERE profiles.id=admin;
 id:=gen_random_uuid();INSERT INTO academic_levels(id,name,value) VALUES(id,'[AUDIT rollback] Level '||id,'audit-'||id);fixture:=fixture||jsonb_build_object('academic_levels',id);
 id:=gen_random_uuid();INSERT INTO departments(id,name,slug,faculty) VALUES(id,'[AUDIT rollback] Department '||id,'audit-'||id,'Audit faculty');fixture:=fixture||jsonb_build_object('departments',id);
 id:=gen_random_uuid();INSERT INTO academic_calendar(id,period_type,name,start_date,end_date,academic_year) VALUES(id,'semester','[AUDIT rollback] Calendar '||id,current_date,current_date+7,'AUDIT');fixture:=fixture||jsonb_build_object('academic_calendar',id);
 id:=gen_random_uuid();INSERT INTO measurement_units(id,name) VALUES(id,'[AUDIT rollback] Unit '||id);fixture:=fixture||jsonb_build_object('measurement_units',id);
 id:=gen_random_uuid();INSERT INTO brand_partnership_requests(id,brand_name,contact_email) VALUES(id,'[AUDIT rollback] Brand '||id,'audit@example.invalid');fixture:=fixture||jsonb_build_object('brand_partnership_requests',id);
 INSERT INTO academic_levels(id,campus_id,name,value) VALUES(own_level,c,'[AUDIT rollback] Own '||own_level,'audit-'||own_level),(foreign_level,other_c,'[AUDIT rollback] Foreign '||foreign_level,'audit-'||foreign_level);
 FOREACH actor IN ARRAY ARRAY[sa,inactive,admin,student] LOOP
  PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
  FOR target IN SELECT * FROM (VALUES('academic_levels','name'),('departments','name'),('academic_calendar','name'),('measurement_units','name'),('brand_partnership_requests','brand_name')) AS v(tbl,col) LOOP
   EXECUTE format('UPDATE public.%I SET %I=%I WHERE id=$1',target.tbl,target.col,target.col) USING (fixture->>target.tbl)::uuid;
   GET DIAGNOSTICS n=ROW_COUNT;
   IF n<>(CASE WHEN actor=sa OR (actor=admin AND target.tbl='brand_partnership_requests') THEN 1 ELSE 0 END) THEN RAISE EXCEPTION 'Global policy boundary failed: % actor % writes %',target.tbl,actor,n;END IF;
  END LOOP;
  IF actor=inactive THEN
   BEGIN
    INSERT INTO measurement_units(name) VALUES('[AUDIT rollback] forbidden insert '||actor);
    RAISE EXCEPTION 'Inactive account inserted a global unit';
   EXCEPTION WHEN insufficient_privilege THEN NULL;END;
   DELETE FROM measurement_units WHERE measurement_units.id=(fixture->>'measurement_units')::uuid;GET DIAGNOSTICS n=ROW_COUNT;
   IF n<>0 THEN RAISE EXCEPTION 'Inactive account deleted a global unit';END IF;
  END IF;
  IF actor=admin THEN
   UPDATE academic_levels SET name=name WHERE academic_levels.id=own_level;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'Active campus admin lost own campus';END IF;
   UPDATE academic_levels SET name=name WHERE academic_levels.id=foreign_level;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Active admin crossed campuses';END IF;
  END IF;
  PERFORM set_config('role','none',true);
 END LOOP;
 -- Deactivate the originally active super admin, retaining the same JWT identity.
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE profiles SET is_active=false WHERE profiles.id=sa;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',sa)::text,true);PERFORM set_config('role','authenticated',true);
 FOR target IN SELECT * FROM(VALUES('academic_levels','name'),('departments','name'),('academic_calendar','name'),('measurement_units','name'),('brand_partnership_requests','brand_name')) AS v(tbl,col) LOOP
  EXECUTE format('UPDATE public.%I SET %I=%I WHERE id=$1',target.tbl,target.col,target.col) USING (fixture->>target.tbl)::uuid;
  GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Reused token retained global privilege: %',target.tbl;END IF;
 END LOOP;
 PERFORM set_config('role','none',true);
END$$;
ROLLBACK;
