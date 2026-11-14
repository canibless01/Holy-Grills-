-- Fresh synthetic rows only. No actual webhook is replayed or maintenance command run.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE ca uuid:=gen_random_uuid(); cb uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); s uuid:=gen_random_uuid(); su uuid:=gen_random_uuid();
 w uuid:=gen_random_uuid(); foreign_w uuid:=gen_random_uuid(); global_w uuid:=gen_random_uuid(); e uuid:=gen_random_uuid(); draft uuid:=gen_random_uuid();
 t uuid:=gen_random_uuid(); hidden_t uuid:=gen_random_uuid(); inactive_t uuid:=gen_random_uuid(); n integer; r record;
BEGIN
 FOR r IN SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p') LOOP
  IF has_table_privilege('anon',r.oid,'TRUNCATE,TRIGGER,REFERENCES') OR has_table_privilege('authenticated',r.oid,'TRUNCATE,TRIGGER,REFERENCES') THEN
   RAISE EXCEPTION 'unneeded maintenance privilege remains on %',r.oid::regclass; END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) x WHERE d.defaclrole='postgres'::regrole AND d.defaclnamespace='public'::regnamespace AND d.defaclobjtype='r' AND x.grantee IN(0,'anon'::regrole,'authenticated'::regrole) AND x.privilege_type IN('TRUNCATE','TRIGGER','REFERENCES')) THEN RAISE EXCEPTION 'unsafe application table defaults';END IF;
 IF has_table_privilege('anon','public.webhook_events','INSERT,UPDATE,DELETE') OR has_table_privilege('authenticated','public.webhook_events','INSERT,UPDATE,DELETE') THEN RAISE EXCEPTION 'browser can forge replay payloads';END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Webhook A','audit-webhook-'||ca),(cb,'[AUDIT rollback] Webhook B','audit-webhook-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) SELECT id,'audit-webhook-'||id||'@example.invalid','{}'::jsonb FROM unnest(ARRAY[a,s,su]) AS ids(id);
 UPDATE public.profiles SET campus_id=ca,role='admin' WHERE id=a;
 UPDATE public.profiles SET campus_id=ca,role='student' WHERE id=s;
 UPDATE public.profiles SET campus_id=NULL,role='super_admin' WHERE id=su;
 INSERT INTO public.webhook_events(id,provider,event_type,reference,payload,status,campus_id) VALUES
 (w,'paystack','audit.rollback',w::text,'{}','failed',ca),(foreign_w,'paystack','audit.rollback',foreign_w::text,'{}','failed',cb),(global_w,'paystack','audit.rollback',global_w::text,'{}','failed',NULL);
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,location) VALUES
 (e,'[AUDIT rollback] Public','audit-webhook-'||e,now(),now()+interval '1 day',true,ca,'FUTA'),(draft,'[AUDIT rollback] Draft','audit-webhook-'||draft,now(),now()+interval '1 day',false,ca,'FUTA');
 INSERT INTO public.event_ticket_tiers(id,event_id,name,campus_id,is_active) VALUES(t,e,'Visible',ca,true),(hidden_t,draft,'Hidden',ca,true),(inactive_t,e,'Inactive',ca,false);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 SELECT count(*) INTO n FROM public.webhook_events WHERE id IN(w,foreign_w,global_w);IF n<>1 THEN RAISE EXCEPTION 'campus admin webhook visibility incorrect';END IF;
 BEGIN UPDATE public.webhook_events SET payload='{"forged":true}' WHERE id=w;RAISE EXCEPTION 'admin forged stored provider payload';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN DELETE FROM public.webhook_events WHERE id=w;RAISE EXCEPTION 'admin deleted provider receipt';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',s)::text,true);PERFORM set_config('role','authenticated',true);
 SELECT count(*) INTO n FROM public.webhook_events WHERE id IN(w,foreign_w,global_w);IF n<>0 THEN RAISE EXCEPTION 'student read payment payload';END IF;
 SELECT count(*) INTO n FROM public.event_ticket_tiers WHERE id IN(t,hidden_t,inactive_t);IF n<>1 THEN RAISE EXCEPTION 'customer tier visibility incorrect';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"anon"}',true);PERFORM set_config('role','anon',true);
 SELECT count(*) INTO n FROM public.event_ticket_tiers WHERE id IN(t,hidden_t,inactive_t);IF n<>1 THEN RAISE EXCEPTION 'guest tier visibility incorrect';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',su)::text,true);PERFORM set_config('role','authenticated',true);
 SELECT count(*) INTO n FROM public.webhook_events WHERE id IN(w,foreign_w,global_w);IF n<>3 THEN RAISE EXCEPTION 'super admin lost log visibility';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);PERFORM set_config('role','service_role',true);
 UPDATE public.webhook_events SET status='processed' WHERE id=w;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'backend log update blocked';END IF;
 PERFORM set_config('role','none',true);
END $verify$;
ROLLBACK;
SELECT 'PASS: browser maintenance/replay-payload writes denied; scoped admin/student/super log reads, backend updates and public/draft/inactive tier boundaries preserved' AS evidence;
