BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid();
 entries jsonb; result jsonb;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Monthly','audit-monthly-'||c),(other_c,'[AUDIT rollback] Other monthly','audit-monthly-'||other_c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-monthly-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Student"}');
 UPDATE public.profiles SET role='student',campus_id=c,top4_finish_count=2 WHERE id=u;
 entries:=jsonb_build_array(jsonb_build_object('rank',1,'user_id',u,'full_name','[AUDIT rollback] Student','hp_earned',25,'campus_id',c));
 result:=public.hg_finalize_monthly_leaderboard(c,'2099-01',entries,true,true,true,60,30);
 IF (result->>'idempotent')::boolean THEN RAISE EXCEPTION 'first finalization skipped'; END IF;
 IF (SELECT count(*) FROM public.exclusive_spins WHERE user_id=u)<>1
 OR (SELECT sum(credits_remaining) FROM public.free_side_credits WHERE user_id=u)<>3
 OR (SELECT top4_finish_count FROM public.profiles WHERE id=u)<>3
 OR (SELECT count(*) FROM public.hall_of_fame_inductees WHERE user_id=u)<>1
 OR (SELECT count(*) FROM public.leaderboard_reward_fulfillments WHERE user_id=u)<>1 THEN RAISE EXCEPTION 'monthly rewards incomplete'; END IF;
 result:=public.hg_finalize_monthly_leaderboard(c,'2099-01',entries,true,true,true,60,30);
 IF NOT (result->>'idempotent')::boolean OR (SELECT sum(credits_remaining) FROM public.free_side_credits WHERE user_id=u)<>3
 OR (SELECT top4_finish_count FROM public.profiles WHERE id=u)<>3 THEN RAISE EXCEPTION 'replay doubled monthly rewards'; END IF;
 PERFORM public.hg_finalize_monthly_leaderboard(other_c,'2099-01','[]',false,false,false,60,30);
 INSERT INTO public.leaderboard_snapshots(campus_id,period_key,ranking_type,entries) VALUES(c,'2099-01','weekly','[]');
 IF (SELECT count(*) FROM public.leaderboard_snapshots WHERE campus_id in(c,other_c))<>3 THEN RAISE EXCEPTION 'campus/type archive collision'; END IF;
 BEGIN
  PERFORM public.hg_finalize_monthly_leaderboard(c,'2099-02',entries,true,true,true,60,30);
  RAISE EXCEPTION 'controlled failure after monthly grant';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM<>'controlled failure after monthly grant' THEN RAISE; END IF;
 END;
 IF EXISTS(SELECT 1 FROM public.leaderboard_snapshots WHERE campus_id=c AND period_key='2099-02')
 OR (SELECT count(*) FROM public.exclusive_spins WHERE user_id=u)<>1 THEN RAISE EXCEPTION 'failed transaction left partial rewards'; END IF;
 IF has_function_privilege('anon','public.hg_finalize_monthly_leaderboard(uuid,text,jsonb,boolean,boolean,boolean,integer,integer)','EXECUTE')
 OR has_function_privilege('authenticated','public.hg_finalize_monthly_leaderboard(uuid,text,jsonb,boolean,boolean,boolean,integer,integer)','EXECUTE') THEN RAISE EXCEPTION 'monthly grants callable by public'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: monthly archive, configured free sides/spin, third-finish HoF induction/perk, no duplicate rewards on replay, campus/type isolation, atomic rollback and service-only privilege. All fixtures rolled back.' as evidence;
