BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); u uuid; users uuid[]:=ARRAY[gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid()];
 m uuid:=gen_random_uuid(); zero_m uuid:=gen_random_uuid(); foreign_m uuid:=gen_random_uuid(); weekly_m uuid:=gen_random_uuid(); legacy_m uuid:=gen_random_uuid(); completion uuid;
 cap integer; month_key text:=to_char(now() AT TIME ZONE 'UTC','YYYY-MM'); r jsonb; again jsonb;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Social','audit-social-'||c),(other_c,'[AUDIT rollback] Other','audit-social-'||other_c);
 FOREACH u IN ARRAY users LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-social-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Social"}');
  UPDATE public.profiles SET campus_id=c,role='student' WHERE id=u;
 END LOOP;
 INSERT INTO public.milestones(id,title,trigger_type,trigger_value,hp_awarded,is_active,campus_id,time_window) VALUES
 (m,'Social','social_follow',1,50,true,c,NULL),(zero_m,'Zero','social_follow',1,0,true,c,NULL),
 (foreign_m,'Foreign','social_follow',1,50,true,other_c,NULL),(weekly_m,'Weekly','social_follow',1,20,true,c,'weekly'),(legacy_m,'Legacy','social_follow',1,10,true,c,NULL);
 BEGIN PERFORM public.hg_complete_pending_milestone(users[1],m,NULL,50); RAISE EXCEPTION 'controlled interruption'; EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled interruption' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.user_milestones WHERE user_id=users[1]) OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=users[1])
 OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=users[1]) THEN RAISE EXCEPTION 'partial social reward after interruption'; END IF;
 r:=public.hg_complete_pending_milestone(users[1],m,NULL,50);
 IF r->>'hp_awarded'<>'50' OR r->>'hp_destination'<>'pending' OR (SELECT hp_balance FROM public.profiles WHERE id=users[1])<>0
 OR (SELECT total_earned FROM public.monthly_hp_tracker WHERE user_id=users[1] AND month=month_key)<>50 THEN RAISE EXCEPTION 'pending destination/tracker incorrect'; END IF;
 UPDATE public.milestones SET hp_awarded=999 WHERE id=m;
 again:=public.hg_complete_pending_milestone(users[1],m,NULL,999);
 IF NOT (again->>'replayed')::boolean OR again->>'hp_awarded'<>'0' OR again->>'recorded_hp_awarded'<>'50'
 OR (SELECT count(*) FROM public.hp_transactions WHERE user_id=users[1])<>1 THEN RAISE EXCEPTION 'replay changed reward'; END IF;
 SELECT (value #>> '{}')::integer INTO cap FROM public.system_settings WHERE key='monthly_pending_cap' AND campus_id IS NULL;
 INSERT INTO public.monthly_hp_tracker(user_id,month,total_earned) VALUES(users[2],month_key,cap-7),(users[3],month_key,cap);
 r:=public.hg_complete_pending_milestone(users[2],m,NULL,50);
 IF r->>'recorded_hp_awarded'<>'7' OR NOT (r->>'capped')::boolean OR (SELECT total_earned FROM public.monthly_hp_tracker WHERE user_id=users[2] AND month=month_key)<>cap THEN RAISE EXCEPTION 'partial cap incorrect'; END IF;
 r:=public.hg_complete_pending_milestone(users[3],m,NULL,50);
 IF r->>'recorded_hp_awarded'<>'0' OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=users[3]) THEN RAISE EXCEPTION 'full cap incorrectly credited'; END IF;
 again:=public.hg_complete_pending_milestone(users[3],m,NULL,999);
 IF again->>'recorded_hp_awarded'<>'0' THEN RAISE EXCEPTION 'zero capped promise changed'; END IF;
 r:=public.hg_complete_pending_milestone(users[1],zero_m,NULL,0);
 UPDATE public.milestones SET hp_awarded=999 WHERE id=zero_m;
 IF public.hg_complete_pending_milestone(users[1],zero_m,NULL,999)->>'recorded_hp_awarded'<>'0' THEN RAISE EXCEPTION 'zero reward changed'; END IF;
 BEGIN PERFORM public.hg_complete_pending_milestone(users[1],foreign_m,NULL,50); RAISE EXCEPTION 'TEST foreign accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 BEGIN PERFORM public.hg_complete_pending_milestone(users[1],weekly_m,'wrong-period',20); RAISE EXCEPTION 'TEST wrong period accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 PERFORM public.record_hp_transaction_atomic(users[4],800,'earn','pending','audit','audit',gen_random_uuid(),NULL,'Pending ceiling fixture',c);
 BEGIN PERFORM public.hg_complete_pending_milestone(users[4],m,NULL,50); RAISE EXCEPTION 'TEST pool ceiling exceeded'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.user_milestones WHERE user_id=users[4]) OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=users[4]) THEN RAISE EXCEPTION 'pool ceiling consumed completion'; END IF;
 INSERT INTO public.user_milestones(user_id,milestone_id,hp_awarded,campus_id) VALUES(users[5],legacy_m,10,c) RETURNING id INTO completion;
 r:=public.hg_complete_pending_milestone(users[5],legacy_m,NULL,50);
 IF NOT (r->>'legacy_review_required')::boolean OR (r->>'completed')::boolean OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=users[5]) THEN RAISE EXCEPTION 'ambiguous legacy completion fabricated HP'; END IF;
 PERFORM public.record_hp_transaction_atomic(users[5],10,'earn','pending','challenge','challenge',completion,NULL,'Original social grant',c);
 r:=public.hg_complete_pending_milestone(users[5],legacy_m,NULL,50);
 IF NOT (r->>'legacy_replayed')::boolean OR r->>'recorded_hp_awarded'<>'10' OR (SELECT count(*) FROM public.hp_transactions WHERE user_id=users[5])<>1
 OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=users[5]) THEN RAISE EXCEPTION 'legacy recovery duplicated credit/accounting'; END IF;
 IF has_function_privilege('anon','public.hg_complete_pending_milestone(uuid,uuid,text,integer)','execute') OR has_function_privilege('authenticated','public.hg_complete_pending_milestone(uuid,uuid,text,integer)','execute') THEN RAISE EXCEPTION 'public pending grant'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: atomic pending milestone/ledger/tracker, interruption/replay, partial/full/pool caps, zero/configuration replay, scope/period and conservative legacy recovery; all fixtures rolled back' AS evidence;
