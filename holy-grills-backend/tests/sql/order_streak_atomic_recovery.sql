-- Every fixture is rolled back; no email, push, gateway or new Auth account.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE u uuid;c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();same_week uuid:=gen_random_uuid();gap uuid:=gen_random_uuid();free_order uuid:=gen_random_uuid();
 r jsonb;ref uuid;collision uuid:=gen_random_uuid();balance integer;
BEGIN
 SELECT p.id INTO u FROM public.profiles p LEFT JOIN public.campuses cp ON cp.id=p.campus_id
 WHERE p.full_name ILIKE '%audit%' AND coalesce(cp.name,'') NOT LIKE '[AUDIT PROVIDER%'
 AND NOT EXISTS(SELECT 1 FROM public.orders o WHERE o.user_id=p.id AND o.status::text='delivered') ORDER BY p.id LIMIT 1;
 IF u IS NULL THEN RAISE EXCEPTION 'isolated audit actor required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Ordering streak','audit-streak-'||c);
 UPDATE public.profiles SET campus_id=c,hp_balance=0,is_active=true,role='student' WHERE id=u;
 DELETE FROM public.order_streaks WHERE user_id=u;
 UPDATE public.order_streak_rewards SET is_active=false;
 INSERT INTO public.order_streak_rewards(weeks,hp_awarded,is_active,campus_id) VALUES(1,11,true,NULL),(2,22,true,NULL) ON CONFLICT(weeks) DO UPDATE SET hp_awarded=excluded.hp_awarded,is_active=true,campus_id=NULL;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,delivered_at,hp_credited_at)
 VALUES(a,u,c,'delivered','paid',100,100,'2025-12-22T10:00:00Z',now()),(b,u,c,'delivered','paid',100,100,'2025-12-28T23:30:00Z',now());
 r:=public.hg_process_order_streak_atomic(b,1,'[AUDIT rollback] Ordering streak');
 IF NOT coalesce((r->>'success')::boolean,false) OR r->>'week'<>'2026-01' OR (r->>'streak_weeks')::integer<>2 OR (r->>'hp_awarded')::integer<>22 THEN RAISE EXCEPTION 'delayed year-boundary delivery failed: %',r; END IF;
 r:=public.hg_process_order_streak_atomic(a,1,'[AUDIT rollback] Ordering streak');
 IF NOT coalesce((r->>'success')::boolean,false) OR (r->>'hp_awarded')::integer<>11 OR (SELECT last_order_week FROM public.order_streaks WHERE user_id=u)<>'2026-01' OR (SELECT streak_weeks FROM public.order_streaks WHERE user_id=u)<>2 THEN RAISE EXCEPTION 'older recovery regressed current streak: %',r; END IF;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,delivered_at,hp_credited_at) VALUES(same_week,u,c,'delivered','paid',100,100,'2025-12-30T10:00:00Z',now());
 UPDATE public.order_streak_rewards SET hp_awarded=999 WHERE campus_id IS NULL AND weeks=2 AND is_active;
 r:=public.hg_process_order_streak_atomic(same_week,2,'[AUDIT rollback] Ordering streak');
 IF (r->>'hp_awarded')::integer<>0 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>33 THEN RAISE EXCEPTION 'second delivery paid same week twice: %',r; END IF;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,delivered_at,hp_credited_at) VALUES(gap,u,c,'delivered','paid',100,100,'2026-01-12T10:00:00Z',now());
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holygrills:order_streak:'||u::text||':2026-03');
 INSERT INTO public.hp_transactions(id,user_id,amount,type,status,balance_after,source,reference_type,reference_id,campus_id) VALUES(collision,u,1,'spend','active',33,'audit','streak',ref,c);
 r:=public.hg_process_order_streak_atomic(gap,1,'[AUDIT rollback] Ordering streak');
 IF r->>'error' IS DISTINCT FROM 'order_streak_pending' OR (SELECT last_order_week FROM public.order_streaks WHERE user_id=u)<>'2026-01' OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>33 THEN RAISE EXCEPTION 'failed award advanced state or balance: %',r; END IF;
 UPDATE public.order_streak_rewards SET hp_awarded=999 WHERE campus_id IS NULL AND weeks=1 AND is_active;
 DELETE FROM public.hp_transactions WHERE id=collision;
 r:=public.hg_process_order_streak_atomic(gap,99,'[AUDIT rollback] Ordering streak');
 IF NOT coalesce((r->>'success')::boolean,false) OR (r->>'streak_weeks')::integer<>1 OR (r->>'hp_awarded')::integer<>11 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>44 THEN RAISE EXCEPTION 'retry changed saved reward or failed reset: %',r; END IF;
 r:=public.hg_process_order_streak_atomic(gap,99,'[AUDIT rollback] Ordering streak');
 IF NOT coalesce((r->>'replayed')::boolean,false) OR (r->>'hp_awarded')::integer<>0 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>44 THEN RAISE EXCEPTION 'replay duplicated streak HP'; END IF;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,delivered_at,hp_credited_at) VALUES(free_order,u,c,'delivered','paid',0,0,'2026-01-19T10:00:00Z',now());
 r:=public.hg_process_order_streak_atomic(free_order,1,'[AUDIT rollback] Ordering streak');
 IF r->>'error' IS DISTINCT FROM 'qualifying_delivery_required' THEN RAISE EXCEPTION 'free reward order counted as paid food'; END IF;
 IF (SELECT sum(amount) FROM public.hp_transactions WHERE user_id=u AND source='streak' AND reference_id IN(SELECT (metadata->'order_streak_recovery'->'result'->>'reference_id')::uuid FROM public.order_status_logs WHERE order_id=ANY(ARRAY[a,b,same_week,gap])))<>44 THEN RAISE EXCEPTION 'weekly ledger conservation failed'; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',u)::text,true);PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.order_status_logs WHERE order_id=b AND metadata ? 'order_streak_recovery') THEN RAISE EXCEPTION 'private streak receipt exposed'; END IF;
 PERFORM set_config('role','none',true);
 IF has_function_privilege('authenticated','public.hg_process_order_streak_atomic(uuid,numeric,text)','EXECUTE') OR has_function_privilege('anon','public.hg_process_order_streak_atomic(uuid,numeric,text)','EXECUTE') THEN RAISE EXCEPTION 'direct browser financial grant exposed'; END IF;
END $audit$;
ROLLBACK;
SELECT 'Ordering streak: WAT/ISO year boundary, delayed/out-of-order delivery, once/week, saved retry terms, failure rollback, missed-week reset, zero-food refusal and private service-only recovery passed; fixtures rolled back' AS evidence;
