BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); manager uuid:=gen_random_uuid(); admin uuid:=gen_random_uuid();
 student uuid:=gen_random_uuid(); other uuid:=gen_random_uuid(); mid uuid:=gen_random_uuid(); interrupted uuid:=gen_random_uuid(); result jsonb; again jsonb;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Promo','audit-promo-'||c),(c2,'[AUDIT rollback] Other','audit-promo-'||c2);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(manager,'audit-promo-'||manager||'@example.invalid','{}'),(admin,'audit-promo-'||admin||'@example.invalid','{}'),(student,'audit-promo-'||student||'@example.invalid','{}'),(other,'audit-promo-'||other||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='community_manager' WHERE id=manager;
 UPDATE public.profiles SET campus_id=c,role='super_admin' WHERE id=admin;
 UPDATE public.profiles SET campus_id=c,role='student' WHERE id=student;
 UPDATE public.profiles SET campus_id=c2,role='student' WHERE id=other;
 INSERT INTO public.ambassadors(profile_id,campus_id,tagged_by) VALUES(student,c,admin),(other,c2,admin);
 result:=public.hg_create_ambassador_promo_atomic(manager,mid,c,'Share {{link}}',null,'2026-11',true,'{}');
 IF (result->>'recipient_count')::integer<>1 OR NOT EXISTS(SELECT 1 FROM public.ambassador_promo_assignments WHERE message_id=mid AND ambassador_id=student)
 OR EXISTS(SELECT 1 FROM public.ambassador_promo_assignments WHERE message_id=mid AND ambassador_id=other) THEN RAISE EXCEPTION 'campus promo leaked: %',result; END IF;
 again:=public.hg_create_ambassador_promo_atomic(manager,mid,c,'Share {{link}}',null,'2026-11',true,'{}');
 IF NOT (again->>'idempotent')::boolean OR (SELECT count(*) FROM public.ambassador_promo_assignments WHERE message_id=mid)<>1 THEN RAISE EXCEPTION 'promo replay duplicated recipients'; END IF;
 again:=public.hg_create_ambassador_promo_atomic(manager,mid,c,'Changed {{link}}',null,'2026-11',true,'{}');
 IF again->>'error'<>'promo_intent_conflict' THEN RAISE EXCEPTION 'changed intent was accepted'; END IF;
 again:=public.hg_create_ambassador_promo_atomic(manager,gen_random_uuid(),c,'Foreign {{link}}',null,'2026-11',false,ARRAY[other]);
 IF again->>'error'<>'promo_no_targets' THEN RAISE EXCEPTION 'foreign target accepted'; END IF;
 again:=public.hg_create_ambassador_promo_atomic(student,gen_random_uuid(),c,'Student {{link}}',null,'2026-11',true,'{}');
 IF again->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'student created staff promo'; END IF;
 -- A scoped super admin remains scoped; explicit NULL is their global choice.
 again:=public.hg_create_ambassador_promo_atomic(admin,gen_random_uuid(),c,'Scoped {{link}}',null,'2026-11',true,'{}');
 IF (again->>'recipient_count')::integer<>1 THEN RAISE EXCEPTION 'selected super-admin campus ignored'; END IF;
 again:=public.hg_create_ambassador_promo_atomic(admin,gen_random_uuid(),null,'Global {{link}}',null,'2026-11',true,'{}');
 IF (again->>'recipient_count')::integer<2 OR NOT (again->'ambassador_ids' @> to_jsonb(ARRAY[student,other])) OR again->'message'->>'campus_id' IS NOT NULL THEN RAISE EXCEPTION 'explicit global super-admin distribution failed'; END IF;
 BEGIN
   PERFORM public.hg_create_ambassador_promo_atomic(manager,interrupted,c,'Interrupted {{link}}',null,'2026-11',false,ARRAY[student]);
   RAISE EXCEPTION 'controlled rollback after distribution';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM<>'controlled rollback after distribution' THEN RAISE; END IF;
 END;
 IF EXISTS(SELECT 1 FROM public.ambassador_promo_messages WHERE id=interrupted) OR EXISTS(SELECT 1 FROM public.ambassador_promo_assignments WHERE message_id=interrupted) THEN RAISE EXCEPTION 'interrupted distribution left partial data'; END IF;
 UPDATE public.profiles SET is_active=false WHERE id=manager;
 again:=public.hg_create_ambassador_promo_atomic(manager,gen_random_uuid(),c,'Inactive {{link}}',null,'2026-11',true,'{}');
 IF again->>'error'<>'promo_forbidden' THEN RAISE EXCEPTION 'inactive manager sent promo'; END IF;
 IF has_function_privilege('anon','public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[])','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_create_ambassador_promo_atomic(uuid,uuid,uuid,text,text,text,boolean,uuid[])','EXECUTE') THEN RAISE EXCEPTION 'public promo mutation allowed'; END IF;
END $$;
ROLLBACK;
SELECT 'atomic scoped distribution, response replay, interruption, roles and permissions passed; fixtures rolled back' AS evidence;
