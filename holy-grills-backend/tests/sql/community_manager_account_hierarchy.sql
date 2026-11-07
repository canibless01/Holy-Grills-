-- Owner-confirmed hierarchy. Preserve the existing database permissions.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();actor uuid:=gen_random_uuid();manager uuid:=gen_random_uuid();foreign_manager uuid:=gen_random_uuid();admin_target uuid:=gen_random_uuid();super_target uuid:=gen_random_uuid();n integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Manager A','audit-manager-'||ca),(cb,'[AUDIT rollback] Manager B','audit-manager-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) SELECT id,'audit-manager-'||id||'@example.invalid','{"full_name":"[AUDIT rollback] Staff hierarchy"}'::jsonb FROM unnest(ARRAY[actor,manager,foreign_manager,admin_target,super_target]) AS ids(id);
 UPDATE public.profiles SET campus_id=ca,role='admin' WHERE id IN(actor,admin_target);
 UPDATE public.profiles SET campus_id=ca,role='community_manager' WHERE id=manager;
 UPDATE public.profiles SET campus_id=cb,role='community_manager' WHERE id=foreign_manager;
 UPDATE public.profiles SET campus_id=NULL,role='super_admin' WHERE id=super_target;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.profiles SET is_active=false WHERE id=manager;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'campus admin cannot deactivate own manager';END IF;
 UPDATE public.profiles SET is_active=true WHERE id=manager;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'campus admin cannot reactivate own manager';END IF;
 UPDATE public.profiles SET is_active=false WHERE id=foreign_manager;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'foreign manager changed';END IF;
 BEGIN UPDATE public.profiles SET is_active=false WHERE id=admin_target;RAISE EXCEPTION 'peer admin changed';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN UPDATE public.profiles SET is_active=false WHERE id=super_target;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'super admin changed';END IF;EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',manager)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.profiles SET full_name='[AUDIT rollback] Own display name' WHERE id=manager;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'manager own profile edit blocked';END IF;
 PERFORM set_config('role','none',true);
END $verify$;
ROLLBACK;
SELECT 'PASS: existing DB hierarchy permits own-campus community-manager deactivation/reactivation, denies foreign/peer-admin/super-admin changes, and retains manager self-profile editing' AS evidence;
