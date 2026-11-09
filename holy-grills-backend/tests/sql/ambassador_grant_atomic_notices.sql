-- Synthetic financial/notification acceptance; every fixture is rolled back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $test$
DECLARE campus uuid:=gen_random_uuid();actor uuid:=gen_random_uuid();student uuid:=gen_random_uuid();
 milestone uuid:=gen_random_uuid();claim uuid:=gen_random_uuid();rejected_claim uuid:=gen_random_uuid();
 result jsonb; original jsonb; intent text:=gen_random_uuid()::text; hp_before integer;count_before integer;
 legacy uuid:=gen_random_uuid();legacy_notice uuid:=gen_random_uuid(); expected uuid;reward_id uuid;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(campus,'[AUDIT rollback] Grant reliability','audit-grant-'||campus);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-grant-'||actor||'@example.invalid','{}'),(student,'audit-grant-'||student||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=campus,is_active=true,push_enabled=true WHERE id IN(actor,student);
 UPDATE public.profiles SET role='super_admin' WHERE id=actor;
 INSERT INTO public.ambassadors(profile_id,campus_id,tagged_by) VALUES(student,campus,actor);
 INSERT INTO public.wallets(user_id,balance,currency,campus_id) VALUES(student,1000,'NGN',campus) ON CONFLICT(user_id) DO NOTHING;
 INSERT INTO public.notification_preferences(user_id,hp_updates,push_enabled) VALUES(student,true,true)
 ON CONFLICT(user_id) DO UPDATE SET hp_updates=true,push_enabled=true;
 INSERT INTO public.ambassador_milestones(id,campus_id,metric,threshold,reward_type,reward_amount,created_by) VALUES(milestone,campus,'orders',1,'hp',50,actor);
 INSERT INTO public.ambassador_milestone_claims(id,milestone_id,ambassador_id,period_month) VALUES(claim,milestone,student,'2026-11');
 SELECT hp_balance INTO hp_before FROM public.profiles WHERE id=student;
 original:=public.hg_issue_ambassador_grant_atomic(actor,student,'hp',50,'2026-11','[AUDIT rollback] Milestone',14,1,'milestone',claim,false,intent);
 reward_id:=(original->>'id')::uuid;
 IF reward_id IS NULL OR (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+50 THEN RAISE EXCEPTION 'Grant/HP did not commit'; END IF;
 IF (SELECT count(*) FROM notifications WHERE user_id=student AND reference_id=reward_id)<>2
 OR (SELECT count(*) FROM notification_deliveries WHERE user_id=student AND notification_id IN(SELECT id FROM notifications WHERE reference_id=reward_id) AND status='queued')<>1
 THEN RAISE EXCEPTION 'Committed grant missing in-app/push durable capture'; END IF;
 expected:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:request-notification:'||student||':ambassador_grant_issued:ambassador_grant:'||reward_id||':push');
 IF NOT EXISTS(SELECT 1 FROM notifications WHERE id=expected AND action_url='/rewards' AND metadata->>'reference_id'=reward_id::text) THEN RAISE EXCEPTION 'Receipt identity/destination mismatch'; END IF;
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(public.hg_due_notification_dispatch(100)) id WHERE id=expected::text) THEN RAISE EXCEPTION 'Lost Python wake cannot recover'; END IF;
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'hp',50,'2026-11','[AUDIT rollback] Milestone',14,1,'milestone',claim,false,intent);
 IF result->>'id'<>original->>'id' OR NOT(result->>'idempotent')::boolean
 OR (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+50
 OR (SELECT count(*) FROM notifications WHERE user_id=student AND reference_id=reward_id)<>2 THEN RAISE EXCEPTION 'Replay changed reward or notice'; END IF;
 BEGIN
  PERFORM public.hg_issue_ambassador_grant_atomic(actor,student,'hp',25,'2026-11','[AUDIT rollback] Changed config',14,1,'milestone',claim,true,gen_random_uuid()::text);
  RAISE EXCEPTION 'Issued claim awarded twice';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'ambassador_claim_already_issued' THEN RAISE; END IF; END;
 IF (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+50 OR (SELECT count(*) FROM ambassador_grants WHERE milestone_claim_id=claim)<>1 THEN RAISE EXCEPTION 'Second claim award leaked'; END IF;
 BEGIN
  PERFORM public.hg_issue_ambassador_grant_atomic(actor,student,'hp',25,'2026-12','[AUDIT rollback] Wrong month',14,1,'milestone',claim,true,gen_random_uuid()::text);
  RAISE EXCEPTION 'Wrong month accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'ambassador_claim_invalid' THEN RAISE; END IF; END;
 INSERT INTO public.ambassador_milestone_claims(id,milestone_id,ambassador_id,period_month,status) VALUES(rejected_claim,milestone,student,'2026-12','rejected');
 BEGIN
  PERFORM public.hg_issue_ambassador_grant_atomic(actor,student,'hp',25,'2026-12','[AUDIT rollback] Rejected',14,1,'milestone',rejected_claim,true,gen_random_uuid()::text);
  RAISE EXCEPTION 'Rejected claim accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'ambassador_claim_rejected' THEN RAISE; END IF; END;
 -- Explicit additional manual grants remain supported, without reusing a claim.
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'hp',25,'2026-11','[AUDIT rollback] Extra manual',14,1,'manual',NULL,true,gen_random_uuid()::text);
 IF (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+75 THEN RAISE EXCEPTION 'Manual override broken'; END IF;
 -- All three categories use the same durable capture.
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'free_side',2,'2026-11','[AUDIT rollback] Sides',14,1,'manual',NULL,false,gen_random_uuid()::text);
 IF NOT EXISTS(SELECT 1 FROM free_side_credits WHERE id=(result->>'free_side_grant_id')::uuid AND credits_remaining=2)
 OR (SELECT count(*) FROM notifications WHERE reference_id=(result->>'id')::uuid)<>2 THEN RAISE EXCEPTION 'Free-side capture incomplete'; END IF;
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'meal_discount',3000,'2026-11','[AUDIT rollback] Meal',14,1,'manual',NULL,false,gen_random_uuid()::text);
 IF NOT EXISTS(SELECT 1 FROM ambassador_meal_discounts WHERE id=(result->>'meal_discount_id')::uuid AND max_meal_value=3000 AND uses_remaining=1)
 OR (SELECT count(*) FROM notifications WHERE reference_id=(result->>'id')::uuid)<>2 THEN RAISE EXCEPTION 'Meal capture incomplete'; END IF;
 -- Notification-insert failure must roll back the earlier benefit/grant.
 SELECT count(*) INTO count_before FROM public.ambassador_grants WHERE ambassador_id=student;
 EXECUTE 'CREATE FUNCTION pg_temp.fail_ambassador_notice() RETURNS trigger LANGUAGE plpgsql AS $f$BEGIN IF NEW.type=''ambassador_grant_issued'' AND NEW.channel=''push'' THEN RAISE EXCEPTION ''simulated_notice_failure''; END IF;RETURN NEW;END$f$';
 CREATE TRIGGER audit_fail_amb_notice BEFORE INSERT ON public.notifications FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_ambassador_notice();
 BEGIN
  PERFORM public.hg_issue_ambassador_grant_atomic(actor,student,'hp',30,'2026-11','[AUDIT rollback] Interrupted capture',14,1,'manual',NULL,true,gen_random_uuid()::text);
  RAISE EXCEPTION 'Capture failure accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'simulated_notice_failure' THEN RAISE; END IF; END;
 DROP TRIGGER audit_fail_amb_notice ON public.notifications;
 IF (SELECT count(*) FROM ambassador_grants WHERE ambassador_id=student)<>count_before OR (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+75 THEN RAISE EXCEPTION 'Capture failure retained partial reward'; END IF;
 -- Opting out suppresses notification channels, never the earned benefit.
 UPDATE notification_preferences SET hp_updates=false WHERE user_id=student;
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'hp',10,'2026-11','[AUDIT rollback] Opt-out',14,1,'manual',NULL,true,gen_random_uuid()::text);
 IF (SELECT hp_balance FROM profiles WHERE id=student)<>hp_before+85 OR EXISTS(SELECT 1 FROM notifications WHERE reference_id=(result->>'id')::uuid) THEN RAISE EXCEPTION 'HP preference ignored or award suppressed'; END IF;
 UPDATE notification_preferences SET hp_updates=true,push_enabled=false WHERE user_id=student;
 result:=public.hg_issue_ambassador_grant_atomic(actor,student,'hp',10,'2026-11','[AUDIT rollback] Push opt-out',14,1,'manual',NULL,true,gen_random_uuid()::text);
 IF (SELECT count(*) FROM notifications WHERE reference_id=(result->>'id')::uuid AND channel='in_app')<>1
 OR EXISTS(SELECT 1 FROM notification_deliveries WHERE notification_id IN(SELECT id FROM notifications WHERE reference_id=(result->>'id')::uuid)) THEN RAISE EXCEPTION 'Push opt-out ignored'; END IF;
 -- An old random-ID push must be adopted, not duplicated by recovery.
 INSERT INTO ambassador_grants(id,ambassador_id,month,reward_category,amount,reason,issued_by,idempotency_key)
 VALUES(legacy,student,'2025-01','hp',10,'[AUDIT rollback] Legacy',actor,gen_random_uuid()::text);
 INSERT INTO notifications(id,user_id,type,title,body,channel,reference_id) VALUES(legacy_notice,student,'ambassador_grant_issued','Legacy notice','Already saved','push',legacy);
 UPDATE notification_preferences SET push_enabled=true WHERE user_id=student;
 PERFORM hg_internal.capture_ambassador_grant_notice(legacy);
 PERFORM hg_internal.capture_ambassador_grant_notice(legacy);
 IF (SELECT count(*) FROM notifications WHERE reference_id=legacy AND channel='push')<>1 OR EXISTS(SELECT 1 FROM notification_deliveries WHERE notification_id=legacy_notice) THEN RAISE EXCEPTION 'Legacy notice resent'; END IF;
 UPDATE ambassador_grants SET status='voided' WHERE id=legacy;
 DELETE FROM notifications WHERE reference_id=legacy AND channel='in_app';
 PERFORM hg_internal.capture_ambassador_grant_notice(legacy);
 IF EXISTS(SELECT 1 FROM notifications WHERE reference_id=legacy AND channel='in_app') THEN RAISE EXCEPTION 'Voided receipt recreated'; END IF;
 IF has_function_privilege('anon','hg_internal.capture_ambassador_grant_notice(uuid)','EXECUTE') OR has_function_privilege('authenticated','hg_internal.capture_ambassador_grant_notice(uuid)','EXECUTE') THEN RAISE EXCEPTION 'Capture helper publicly callable'; END IF;
END $test$;
ROLLBACK;
