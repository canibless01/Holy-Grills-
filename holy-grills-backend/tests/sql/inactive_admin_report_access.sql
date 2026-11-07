BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();payload jsonb;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Report permissions','audit-report-role-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-report-role-'||a||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='admin',is_active=true WHERE id=a;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 payload:=public.get_hp_program_report_summary(current_date);IF payload->>'total_issued'<>'0' THEN RAISE EXCEPTION 'report is not isolated to fresh campus';END IF;
 payload:=public.get_pending_squad_hp_report(14);IF payload->>'pending_count'<>'0' THEN RAISE EXCEPTION 'pending report is not isolated';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE public.profiles SET is_active=false WHERE id=a;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 BEGIN PERFORM public.get_hp_program_report_summary(current_date);RAISE EXCEPTION 'inactive admin accessed HP report';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM public.get_pending_squad_hp_report(14);RAISE EXCEPTION 'inactive admin accessed private pending report';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 PERFORM set_config('role','none',true);
END $verify$;
ROLLBACK;
SELECT 'PASS: active campus-admin reports remain scoped; deactivated accounts with existing claims cannot call either report directly' AS evidence;
