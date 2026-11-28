BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE ca uuid:=gen_random_uuid(); cb uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); s uuid:=gen_random_uuid(); u uuid:=gen_random_uuid();
 one uuid:=gen_random_uuid(); two uuid:=gen_random_uuid(); global_row uuid:=gen_random_uuid(); n integer; stamp timestamptz:='2026-01-01T00:00:00Z';
BEGIN
 INSERT INTO campuses(id,name,slug,is_active) VALUES(ca,'[AUDIT rollback] CMS A','audit-'||ca,true),(cb,'[AUDIT rollback] CMS B','audit-'||cb,true);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-cms-'||a||'@example.invalid','{}'),(s,'audit-cms-'||s||'@example.invalid','{}'),(u,'audit-cms-'||u||'@example.invalid','{}');
 UPDATE profiles SET campus_id=ca,is_active=true WHERE id IN(a,s,u); UPDATE profiles SET role='admin' WHERE id=a; UPDATE profiles SET role='super_admin' WHERE id=s;
 INSERT INTO storefront_sections(id,campus_id,key,section_type,title,content,is_active,updated_at) VALUES
 (one,ca,'audit-'||one,'our_story','Original','{"custom":"Keep"}',true,stamp),
 (two,cb,'audit-'||two,'our_story','Foreign','{}',true,stamp),
 (global_row,null,'audit-'||global_row,'our_story','Global','{}',true,stamp);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true); EXECUTE 'SET LOCAL ROLE authenticated';
 UPDATE storefront_sections SET title='Saved',updated_at=stamp+interval '1 second' WHERE id=one AND updated_at=stamp;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'Own campus save rejected'; END IF;
 UPDATE storefront_sections SET title='Stale' WHERE id=one AND updated_at=stamp;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Stale edit overwrote newer row'; END IF;
 UPDATE storefront_sections SET title='Forged' WHERE id IN(two,global_row);GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Campus admin changed foreign/global CMS'; END IF;
 IF (SELECT content->>'custom' FROM storefront_sections WHERE id=one)<>'Keep' THEN RAISE EXCEPTION 'Custom content lost'; END IF;
 EXECUTE 'RESET ROLE';PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 UPDATE storefront_sections SET title='Student write' WHERE id=one;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Student mutated CMS'; END IF;
 EXECUTE 'RESET ROLE';PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',s)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 UPDATE storefront_sections SET title='Platform edit' WHERE id IN(two,global_row);GET DIAGNOSTICS n=ROW_COUNT;IF n<>2 THEN RAISE EXCEPTION 'Super admin scope failed'; END IF;
 EXECUTE 'RESET ROLE';UPDATE profiles SET is_active=false WHERE id=a;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);EXECUTE 'SET LOCAL ROLE authenticated';
 UPDATE storefront_sections SET title='Inactive write' WHERE id=one;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'Inactive admin mutated CMS'; END IF;
 EXECUTE 'RESET ROLE';
END $$;
ROLLBACK;
