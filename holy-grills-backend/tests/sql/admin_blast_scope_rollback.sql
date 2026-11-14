BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();a uuid:=gen_random_uuid();s uuid:=gen_random_uuid();u uuid:=gen_random_uuid();one uuid:=gen_random_uuid();two uuid:=gen_random_uuid();global_blast uuid:=gen_random_uuid();n integer;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Blast A','audit-'||ca),(cb,'[AUDIT rollback] Blast B','audit-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-blast-'||a||'@example.invalid','{}'),(s,'audit-blast-'||s||'@example.invalid','{}'),(u,'audit-blast-'||u||'@example.invalid','{}');UPDATE profiles SET campus_id=ca,is_active=true WHERE id IN(a,s,u);UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='super_admin' WHERE id=s;
 INSERT INTO notification_blasts(id,campus_id,created_by,title,body,channels,segment,status,scheduled_at) VALUES(one,ca,a,'A','Body',ARRAY['in_app'],'{}','scheduled',now()+interval '1 day'),(two,cb,s,'B','Body',ARRAY['in_app'],'{}','scheduled',now()+interval '1 day'),(global_blast,null,s,'Global','Body',ARRAY['in_app'],'{}','scheduled',now()+interval '1 day');
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 SELECT count(*) INTO n FROM notification_blasts WHERE id IN(one,two,global_blast);IF n<>1 THEN RAISE EXCEPTION 'Campus admin blast read leaked';END IF;
 BEGIN INSERT INTO notification_blasts(campus_id,created_by,title,body,channels,segment,status) VALUES(ca,a,'Forged segment','Body',ARRAY['in_app'],jsonb_build_object('campus_id',cb),'pending');RAISE EXCEPTION 'Foreign segment inserted directly';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 UPDATE notification_blasts SET status='cancelled' WHERE id=two;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Foreign blast modified';END IF;
 EXECUTE 'RESET ROLE';PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 SELECT count(*) INTO n FROM notification_blasts WHERE id IN(one,two,global_blast);IF n<>0 THEN RAISE EXCEPTION 'Student read private campaigns';END IF;
 EXECUTE 'RESET ROLE';PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',s)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 SELECT count(*) INTO n FROM notification_blasts WHERE id IN(one,two,global_blast);IF n<>3 THEN RAISE EXCEPTION 'Super admin lost global access';END IF;
 EXECUTE 'RESET ROLE';PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);UPDATE profiles SET is_active=false WHERE id=a;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 SELECT count(*) INTO n FROM notification_blasts WHERE id IN(one,two,global_blast);IF n<>0 THEN RAISE EXCEPTION 'Inactive admin reused access';END IF;
 EXECUTE 'RESET ROLE';
 IF NOT EXISTS(SELECT 1 FROM pg_policy WHERE polrelid='public.notification_blasts'::regclass AND polname='notification_blasts_segment_scope' AND NOT polpermissive) THEN RAISE EXCEPTION 'Restrictive segment policy lost';END IF;
END $$;
ROLLBACK;
