BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE users uuid[]; u uuid; other uuid; c1 uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); n integer;
BEGIN
 SELECT array_agg(id) INTO users FROM (SELECT id FROM public.profiles WHERE full_name ILIKE '%audit%' AND is_active ORDER BY id LIMIT 2) chosen;
 u:=users[1];other:=users[2];IF other IS NULL THEN RAISE EXCEPTION 'audit identities required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c1,'[AUDIT rollback] Role A','audit-role-'||c1),(c2,'[AUDIT rollback] Role B','audit-role-'||c2);
 UPDATE public.profiles SET role='student',campus_id=CASE WHEN id=u THEN c1 ELSE c2 END WHERE id IN(u,other);
 INSERT INTO public.ambassadors(profile_id,campus_id,status) VALUES(u,c1,'active'),(other,c2,'active')
 ON CONFLICT(profile_id) DO UPDATE SET campus_id=excluded.campus_id,status='active';
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF NOT EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=u) OR EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=other) THEN RAISE EXCEPTION 'student isolation failed'; END IF;
 BEGIN
   UPDATE public.ambassadors SET status='inactive' WHERE profile_id=u;
   RAISE EXCEPTION 'student write unexpectedly allowed';
 EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE public.profiles SET role='admin' WHERE id=u;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=other) THEN RAISE EXCEPTION 'campus admin crossed campus'; END IF;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE public.profiles SET role='super_admin' WHERE id=u;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF NOT EXISTS(SELECT 1 FROM public.ambassadors WHERE profile_id=other) THEN RAISE EXCEPTION 'super admin global read failed'; END IF;
 -- Actual authenticated super-admin can assign the newly supported enum role.
 UPDATE public.profiles SET role='community_manager' WHERE id=other;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=other AND role::text='community_manager') THEN RAISE EXCEPTION 'community manager assignment failed'; END IF;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',other)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF NOT public.hg_is_ambassador_staff(c2) OR public.hg_is_ambassador_staff(c1) OR public.hg_is_financial_admin() THEN RAISE EXCEPTION 'community manager campus/financial boundaries failed'; END IF;

 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE public.profiles SET is_active=false WHERE id=u;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF public.hg_is_ambassador_staff(c2) THEN RAISE EXCEPTION 'inactive staff kept privileges'; END IF;
 PERFORM set_config('role','none',true);
END $$;
ROLLBACK;
SELECT 'actual authenticated student/campus-admin/super-admin/inactive roles passed; fixtures rolled back' AS evidence;
