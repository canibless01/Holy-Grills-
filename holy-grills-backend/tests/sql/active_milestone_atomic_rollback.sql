BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); a uuid:=gen_random_uuid();
 m uuid:=gen_random_uuid(); zero_m uuid:=gen_random_uuid(); monthly uuid:=gen_random_uuid(); admin_m uuid:=gen_random_uuid();
 legacy uuid:=gen_random_uuid(); legacy_paid uuid:=gen_random_uuid(); um_id uuid:=gen_random_uuid();
 r jsonb; b integer; tracked integer; period text:=to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM');
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Milestones','audit-milestone-'||c),(other_c,'[AUDIT rollback] Other milestones','audit-milestone-'||other_c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-milestone-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Milestone student"}'),(a,'audit-milestone-'||a||'@example.invalid','{"full_name":"[AUDIT rollback] Milestone admin"}');
 UPDATE public.profiles SET campus_id=c,role='student',is_active=true WHERE id IN(u,a);
 INSERT INTO public.milestones(id,title,trigger_type,trigger_value,hp_awarded,is_active,campus_id,time_window)
 VALUES(m,'[AUDIT rollback] First','first_order',1,30,true,c,NULL),(zero_m,'[AUDIT rollback] Zero','first_order',1,0,true,c,NULL),
 (monthly,'[AUDIT rollback] Month','order_count',1,15,true,c,'monthly'),(admin_m,'[AUDIT rollback] Admin','department_leader',1,40,true,c,NULL),
 (legacy,'[AUDIT rollback] Legacy','first_order',1,99,true,c,NULL),(legacy_paid,'[AUDIT rollback] Historical paid','first_order',1,99,true,c,NULL);
 SELECT hp_balance INTO b FROM public.profiles WHERE id=u;
 SELECT coalesce(sum(total_earned),0) INTO tracked FROM public.monthly_hp_tracker WHERE user_id=u;
 BEGIN
  PERFORM public.hg_complete_active_milestone(u,m,NULL,30,NULL);
  RAISE EXCEPTION 'controlled grant interruption';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled grant interruption' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.user_milestones WHERE user_id=u) OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=u)
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>b THEN RAISE EXCEPTION 'interrupted grant left partial completion or money'; END IF;
 r:=public.hg_complete_active_milestone(u,m,NULL,30,NULL);
 IF NOT (r->>'completed')::boolean OR (r->>'hp_awarded')::integer<>30 OR (r->>'replayed')::boolean THEN RAISE EXCEPTION 'first grant wrong'; END IF;
 IF (SELECT count(*) FROM public.notifications WHERE user_id=u AND type='milestone_achieved')<>2
 OR (SELECT count(*) FROM public.notification_deliveries WHERE user_id=u AND notification_id IN (SELECT id FROM public.notifications WHERE user_id=u AND type='milestone_achieved'))<>1 THEN RAISE EXCEPTION 'milestone notice/outbox did not commit with grant';END IF;
 UPDATE public.milestones SET hp_awarded=999 WHERE id=m;
 r:=public.hg_complete_active_milestone(u,m,NULL,999,NULL);
 IF (r->>'hp_awarded')::integer<>0 OR (r->>'recorded_hp_awarded')::integer<>30 OR NOT (r->>'replayed')::boolean
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>b+30 THEN RAISE EXCEPTION 'replay changed immutable grant'; END IF;
 IF (SELECT sum(total_earned) FROM public.monthly_hp_tracker WHERE user_id=u)<>tracked+30 THEN RAISE EXCEPTION 'counter duplicated'; END IF;
 r:=public.hg_complete_active_milestone(u,zero_m,NULL,0,NULL);
 UPDATE public.milestones SET hp_awarded=60 WHERE id=zero_m;
 r:=public.hg_complete_active_milestone(u,zero_m,NULL,60,NULL);
 IF (r->>'recorded_hp_awarded')::integer<>0 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>b+30 THEN RAISE EXCEPTION 'zero reward changed on replay'; END IF;
 r:=public.hg_complete_active_milestone(u,monthly,period,15,NULL);
 IF (r->>'period_key') IS DISTINCT FROM period THEN RAISE EXCEPTION 'period mismatch'; END IF;
 BEGIN
  PERFORM public.hg_complete_active_milestone(u,admin_m,NULL,40,a);
  RAISE EXCEPTION 'TEST student manual grant allowed';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 UPDATE public.profiles SET role='admin',campus_id=other_c WHERE id=a;
 BEGIN
  PERFORM public.hg_complete_active_milestone(u,admin_m,NULL,40,a);
  RAISE EXCEPTION 'TEST foreign admin grant allowed';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 UPDATE public.profiles SET campus_id=c WHERE id=a;
 r:=public.hg_complete_active_milestone(u,admin_m,NULL,40,a);
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>b+85 THEN RAISE EXCEPTION 'manual grant failed'; END IF;
 INSERT INTO public.user_milestones(user_id,milestone_id,hp_awarded,campus_id) VALUES(u,legacy,999,c);
 r:=public.hg_complete_active_milestone(u,legacy,NULL,500,NULL);
 IF coalesce((r->>'completed')::boolean,false) OR NOT (r->>'legacy_review_required')::boolean THEN RAISE EXCEPTION 'ambiguous legacy row silently paid'; END IF;
 INSERT INTO public.user_milestones(id,user_id,milestone_id,hp_awarded,campus_id) VALUES(um_id,u,legacy_paid,13,c);
 PERFORM public.record_hp_transaction_atomic(u,13,'earn','active','challenge','milestone',um_id,NULL,'Historical milestone',c);
 r:=public.hg_complete_active_milestone(u,legacy_paid,NULL,999,NULL);
 IF (r->>'recorded_hp_awarded')::integer<>13 OR (r->>'hp_awarded')::integer<>0
 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>b+98 THEN RAISE EXCEPTION 'historical ledger paid twice'; END IF;
 IF (SELECT sum(total_earned) FROM public.monthly_hp_tracker WHERE user_id=u)<>tracked+85 THEN RAISE EXCEPTION 'historical tracker fabricated'; END IF;
 IF has_function_privilege('anon','public.hg_complete_active_milestone(uuid,uuid,text,integer,uuid)','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_complete_active_milestone(uuid,uuid,text,integer,uuid)','EXECUTE')
 OR has_table_privilege('authenticated','public.user_milestones','INSERT') THEN RAISE EXCEPTION 'public reward mutation'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: active milestone completion/ledger/tracker atomicity, interruption rollback, unchanged/zero replay, period scope, manual grant roles, conservative legacy reconciliation and service-only mutation; all fixtures rolled back' AS evidence;
