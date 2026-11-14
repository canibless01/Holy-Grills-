BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();a uuid:=gen_random_uuid();s uuid:=gen_random_uuid();u uuid:=gen_random_uuid();r uuid:=gen_random_uuid();r2 uuid:=gen_random_uuid();result jsonb;cancelled_at timestamptz;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Newsletter A','audit-'||ca),(cb,'[AUDIT rollback] Newsletter B','audit-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(a,'audit-newsletter-'||a||'@example.invalid','{}'),(s,'audit-newsletter-'||s||'@example.invalid','{}'),(u,'audit-newsletter-'||u||'@example.invalid','{}');
 UPDATE profiles SET campus_id=ca,is_active=true WHERE id IN(a,s,u);UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='super_admin' WHERE id=s;
 EXECUTE 'SET LOCAL ROLE service_role';result:=hg_queue_newsletter_campaign(a,r,ca,'Launch news','First paragraph'||chr(10)||chr(10)||'Second paragraph');EXECUTE 'RESET ROLE';
 IF result->'campaign'->>'status'<>'queued' THEN RAISE EXCEPTION 'Campaign not queued';END IF;
 result:=hg_queue_newsletter_campaign(a,r,ca,'Launch news','First paragraph'||chr(10)||chr(10)||'Second paragraph');IF NOT(result->>'replayed')::boolean THEN RAISE EXCEPTION 'Lost-response create did not replay';END IF;
 IF (SELECT count(*) FROM newsletter_campaigns WHERE id=r)<>1 OR (SELECT count(*) FROM admin_audit_logs WHERE entity_id=r::text AND action='newsletter_queued')<>1 THEN RAISE EXCEPTION 'Create replay duplicated campaign/audit';END IF;
 BEGIN PERFORM hg_queue_newsletter_campaign(a,r,ca,'Changed subject','Changed body');RAISE EXCEPTION 'Changed intent accepted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_NEWSLETTER_CONFLICT' THEN RAISE;END IF;END;
 BEGIN PERFORM hg_queue_newsletter_campaign(a,gen_random_uuid(),ca,'Launch news','First paragraph'||chr(10)||chr(10)||'Second paragraph');RAISE EXCEPTION 'Different UUID duplicated campaign';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_NEWSLETTER_DUPLICATE' THEN RAISE;END IF;END;
 BEGIN PERFORM hg_queue_newsletter_campaign(a,gen_random_uuid(),null,'Global abuse','Body');RAISE EXCEPTION 'Campus admin queued global campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_queue_newsletter_campaign(a,gen_random_uuid(),cb,'Foreign abuse','Body');RAISE EXCEPTION 'Campus admin queued foreign campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_queue_newsletter_campaign(u,gen_random_uuid(),ca,'Student abuse','Body');RAISE EXCEPTION 'Student queued campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 result:=hg_queue_newsletter_campaign(s,r2,null,'Global campaign','Body');
 BEGIN PERFORM hg_cancel_newsletter_campaign(a,r2,ca);RAISE EXCEPTION 'Campus admin cancelled global campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_cancel_newsletter_campaign(s,r2,cb);RAISE EXCEPTION 'Selected-campus view cancelled hidden global campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 result:=hg_cancel_newsletter_campaign(a,r,ca);cancelled_at:=(result->'campaign'->>'completed_at')::timestamptz;
 result:=hg_cancel_newsletter_campaign(a,r,ca);IF NOT(result->>'replayed')::boolean OR (result->'campaign'->>'completed_at')::timestamptz IS DISTINCT FROM cancelled_at THEN RAISE EXCEPTION 'Cancel retry changed receipt';END IF;
 IF (SELECT count(*) FROM admin_audit_logs WHERE entity_id=r::text AND action='newsletter_cancelled')<>1 THEN RAISE EXCEPTION 'Cancel audit duplicated';END IF;
 UPDATE profiles SET is_active=false WHERE id=a;
 BEGIN PERFORM hg_queue_newsletter_campaign(a,gen_random_uuid(),ca,'Inactive abuse','Body');RAISE EXCEPTION 'Inactive admin queued campaign';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 IF has_function_privilege('anon','public.hg_queue_newsletter_campaign(uuid,uuid,uuid,text,text)','execute') OR has_function_privilege('authenticated','public.hg_cancel_newsletter_campaign(uuid,uuid,uuid)','execute') THEN RAISE EXCEPTION 'Campaign helper exposed';END IF;
END $$;
ROLLBACK;
