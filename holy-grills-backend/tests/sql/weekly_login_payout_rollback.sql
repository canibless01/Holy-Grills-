BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); u uuid; users uuid[]:=ARRAY[gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),gen_random_uuid()];
 monday date:=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date; previous date;
 good jsonb:='{"0":"checked","1":"reclaimed","2":"checked","3":"checked","4":"checked","5":"fraud","7":"checked"}';
 r jsonb; again jsonb; ref uuid; blocker uuid; cap integer; month_key text:=to_char(now() AT TIME ZONE 'UTC','YYYY-MM');
BEGIN
 previous:=monday-7;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Weekly login','audit-weekly-login-'||c);
 INSERT INTO public.feature_flags(feature_name,campus_id,is_active) VALUES('hp_multiplier',c,false);
 INSERT INTO public.system_settings(key,value,campus_id) VALUES('login_streak_rewards','{"1":11,"2":22,"3":33,"4+":44}',c);
 INSERT INTO public.login_streak_rewards(week_number,hp_awarded,is_active,campus_id) VALUES(1,111,true,c),(2,222,true,c),(4,444,true,c) ON CONFLICT(week_number) DO UPDATE SET hp_awarded=EXCLUDED.hp_awarded,is_active=true,campus_id=EXCLUDED.campus_id;
 FOREACH u IN ARRAY users LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-weekly-login-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Weekly login"}');
  UPDATE public.profiles SET campus_id=c,role='student',is_active=true,is_fraud_flagged=false WHERE id=u;
  INSERT INTO public.login_streaks(user_id,current_week_start,week_state,cycle_week_number,consecutive_weeks,streak_count,campus_id)
   VALUES(u,previous,good,1,0,5,c);
 END LOOP;
 -- An interrupted transaction cannot preserve HP while losing advancement, or vice versa.
 BEGIN
  PERFORM public.hg_rollover_login_week(users[1]);
  RAISE EXCEPTION 'controlled weekly interruption';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled weekly interruption' THEN RAISE; END IF; END;
 IF EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=users[1])
 OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=users[1])
 OR (SELECT current_week_start FROM public.login_streaks WHERE user_id=users[1])<>previous THEN RAISE EXCEPTION 'weekly interruption left partial state'; END IF;
 r:=public.hg_rollover_login_week(users[1]);
 IF NOT (r->'receipt'->>'previous_week_completed')::boolean OR r->'receipt'->>'missed_days'<>'2'
 OR r->>'hp_awarded'<>'11' OR r->'streak'->>'cycle_week_number'<>'2' THEN RAISE EXCEPTION 'five valid check-ins did not complete week'; END IF;
 IF (SELECT total_earned FROM public.monthly_hp_tracker WHERE user_id=users[1] AND month=month_key)<>11
 OR (SELECT hp_balance FROM public.profiles WHERE id=users[1])<>0 THEN RAISE EXCEPTION 'weekly tracker or active/pending destination wrong'; END IF;
 UPDATE public.login_streak_rewards SET hp_awarded=999 WHERE campus_id=c AND week_number=1;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','999') WHERE campus_id=c AND key='login_streak_rewards';
 again:=public.hg_rollover_login_week(users[1]);
 IF NOT (again->>'replayed')::boolean OR again->>'hp_awarded'<>'0' OR again->'receipt'->>'hp_awarded'<>'11'
 OR (SELECT count(*) FROM public.hp_transactions WHERE user_id=users[1])<>1 THEN RAISE EXCEPTION 'response-loss retry changed saved reward'; END IF;
 IF public.hg_ack_login_week_notice(users[1],gen_random_uuid()) THEN RAISE EXCEPTION 'wrong notification ack accepted'; END IF;
 PERFORM public.hg_ack_login_week_notice(users[1],(r->'receipt'->>'reference_id')::uuid);
 IF NOT (SELECT (last_week_receipt->>'notified')::boolean FROM public.login_streaks WHERE user_id=users[1]) THEN RAISE EXCEPTION 'receipt acknowledgement failed'; END IF;
 UPDATE public.login_streak_rewards SET hp_awarded=11 WHERE campus_id=c AND week_number=1;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','11') WHERE campus_id=c AND key='login_streak_rewards';
 SELECT coalesce((value #>> '{}')::integer,1000) INTO cap FROM public.system_settings WHERE key='monthly_pending_cap' AND campus_id IS NULL;
 INSERT INTO public.monthly_hp_tracker(user_id,month,total_earned) VALUES(users[2],month_key,cap-7),(users[8],month_key,cap);
 r:=public.hg_rollover_login_week(users[2]);
 IF r->>'hp_awarded'<>'7' OR NOT (r->'receipt'->>'capped')::boolean
 OR (SELECT total_earned FROM public.monthly_hp_tracker WHERE user_id=users[2] AND month=month_key)<>cap THEN RAISE EXCEPTION 'partial cap incorrect'; END IF;
 r:=public.hg_rollover_login_week(users[8]);
 IF r->>'hp_awarded'<>'0' OR NOT (r->'receipt'->>'capped')::boolean
 OR NOT (r->'receipt'->>'previous_week_completed')::boolean THEN RAISE EXCEPTION 'full cap lost valid week'; END IF;
 UPDATE public.login_streak_rewards SET hp_awarded=0 WHERE campus_id=c AND week_number=1;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','0') WHERE campus_id=c AND key='login_streak_rewards';
 r:=public.hg_rollover_login_week(users[3]);
 UPDATE public.login_streak_rewards SET hp_awarded=11 WHERE campus_id=c AND week_number=1;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','11') WHERE campus_id=c AND key='login_streak_rewards';
 again:=public.hg_rollover_login_week(users[3]);
 IF again->'receipt'->>'hp_awarded'<>'0' OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=users[3]) THEN RAISE EXCEPTION 'zero reward changed after settings edit'; END IF;
 -- Malformed configured HP fails closed without consuming the unpaid week.
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','"invalid"') WHERE campus_id=c AND key='login_streak_rewards';
 BEGIN
  PERFORM public.hg_rollover_login_week(users[4]);
  RAISE EXCEPTION 'TEST invalid configured amount accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 IF (SELECT current_week_start FROM public.login_streaks WHERE user_id=users[4])<>previous THEN RAISE EXCEPTION 'invalid configuration advanced week'; END IF;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','11') WHERE campus_id=c AND key='login_streak_rewards';
 -- Existing pending-balance ceiling failures remain recoverable, never a paid week.
 r:=public.record_hp_transaction_atomic(users[4],800,'earn','pending','audit','audit',gen_random_uuid(),NULL,'[AUDIT rollback] Ceiling',c);
 blocker:=(r->>'transaction_id')::uuid;
 BEGIN
  PERFORM public.hg_rollover_login_week(users[4]);
  RAISE EXCEPTION 'TEST ceiling failure ignored';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 IF (SELECT current_week_start FROM public.login_streaks WHERE user_id=users[4])<>previous
 OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=users[4]) THEN RAISE EXCEPTION 'failed HP advanced week or counter'; END IF;
 DELETE FROM public.hp_transactions WHERE id=blocker;
 r:=public.hg_rollover_login_week(users[4]);
 IF r->>'hp_awarded'<>'11' THEN RAISE EXCEPTION 'failed payout did not recover once'; END IF;
 UPDATE public.login_streaks SET week_state='{"0":"checked","1":"checked","2":"checked","3":"checked","4":"fraud","7":"checked"}' WHERE user_id=users[5];
 r:=public.hg_rollover_login_week(users[5]);
 IF (r->'receipt'->>'previous_week_completed')::boolean OR r->'receipt'->>'missed_days'<>'3'
 OR r->'streak'->>'cycle_week_number'<>'1' THEN RAISE EXCEPTION 'four valid days did not reset cycle'; END IF;
 UPDATE public.login_streaks SET current_week_start=monday-14,week_state='{"0":"checked","1":"checked","2":"checked","3":"checked","4":"checked","5":"checked","6":"checked"}',cycle_week_number=4,consecutive_weeks=9 WHERE user_id=users[6];
 r:=public.hg_rollover_login_week(users[6]);
 IF (r->'receipt'->>'previous_week_completed')::boolean OR r->'receipt'->>'missed_days'<>'7'
 OR (r->'receipt'->>'week_start')::date<>previous THEN RAISE EXCEPTION 'skipped week credited an older good week'; END IF;
 -- Missing JSON week keys fall back to the existing reward table.
 UPDATE public.system_settings SET value=value-'1' WHERE campus_id=c AND key='login_streak_rewards';
 UPDATE public.login_streak_rewards SET hp_awarded=17 WHERE campus_id=c AND week_number=1;
 r:=public.hg_rollover_login_week(users[9]);
 IF r->>'hp_awarded'<>'17' THEN RAISE EXCEPTION 'legacy table fallback failed'; END IF;
 UPDATE public.system_settings SET value=jsonb_set(value,'{1}','11') WHERE campus_id=c AND key='login_streak_rewards';
 UPDATE public.login_streak_rewards SET hp_awarded=11 WHERE campus_id=c AND week_number=1;
 -- A previous week-4 payout has a different business reference from this week-4 payout.
 UPDATE public.feature_flags SET is_active=true WHERE feature_name='hp_multiplier' AND campus_id=c;
 INSERT INTO public.system_settings(key,value,campus_id) VALUES('hp_multiplier','2',c);
 UPDATE public.login_streaks SET cycle_week_number=4,consecutive_weeks=8 WHERE user_id=users[7];
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holygrills:login_streak:'||users[7]::text||':'||(previous-7)::text);
 PERFORM public.record_hp_transaction_atomic(users[7],44,'earn','pending','streak','streak',ref,NULL,'Earlier week 4',c);
 r:=public.hg_rollover_login_week(users[7]);
 IF r->>'hp_awarded'<>'88' OR r->'streak'->>'cycle_week_number'<>'4'
 OR (SELECT count(*) FROM public.hp_transactions WHERE user_id=users[7])<>2 THEN RAISE EXCEPTION 'week-4 plateau reused an older payout'; END IF;
 IF has_function_privilege('anon','public.hg_rollover_login_week(uuid)','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_ack_login_week_notice(uuid,uuid)','EXECUTE') THEN RAISE EXCEPTION 'public weekly payout'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: weekly pending HP/tracker/advancement atomicity, five versus four check-ins, exact misses, interruption/response-loss replay, edited/zero rewards, caps, ceiling recovery, skipped weeks, week-4 references, notification acknowledgement and private execution; all fixtures rolled back' AS evidence;
