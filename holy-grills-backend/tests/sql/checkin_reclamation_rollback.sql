BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); other_u uuid:=gen_random_uuid();
 topup uuid:=gen_random_uuid(); low uuid:=gen_random_uuid(); refund uuid:=gen_random_uuid(); foreign_topup uuid:=gen_random_uuid(); old uuid:=gen_random_uuid();
 food uuid:=gen_random_uuid(); unpaid uuid:=gen_random_uuid(); addon_only uuid:=gen_random_uuid();
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
 monday date:=date_trunc('week',now() AT TIME ZONE 'Africa/Lagos')::date;
 receipt_day date; key text; today_key text; r jsonb; base_hp integer; before_state jsonb;
BEGIN
 receipt_day:=greatest(monday,today-1);key:=(receipt_day-monday)::text;today_key:=(today-monday)::text;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Check-in','audit-checkin-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-checkin-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Check-in student"}'),(other_u,'audit-checkin-'||other_u||'@example.invalid','{"full_name":"[AUDIT rollback] Check-in other"}');
 UPDATE public.profiles SET campus_id=c,is_active=true,role='student' WHERE id IN(u,other_u);
 SELECT hp_balance INTO base_hp FROM public.profiles WHERE id=u;
 INSERT INTO public.login_streaks(user_id,current_week_start,week_state,streak_count,cycle_week_number,consecutive_weeks,campus_id)
 VALUES(u,monday,'{}',1,1,0,c);
 INSERT INTO public.wallet_transactions(id,user_id,type,amount,balance_after,reference_type,created_at,campus_id) VALUES
 (topup,u,'credit',1000,1000,'topup',(receipt_day::timestamp AT TIME ZONE 'Africa/Lagos')+interval '30 minutes',c),
 (low,u,'credit',999,1999,'topup',now(),c),(refund,u,'credit',3000,4999,'order_refund',now(),c),
 (foreign_topup,other_u,'credit',3000,3000,'topup',now(),c),
 (old,u,'credit',3000,7999,'topup',((monday-1)::timestamp AT TIME ZONE 'Africa/Lagos'),c);
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',low,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'low top-up reclaimed'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',refund,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'refund reclaimed'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',foreign_topup,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'foreign receipt reclaimed'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',old,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'old replay reclaimed current week'; END IF;
 BEGIN
  PERFORM public.hg_reclaim_login_checkin(u,'wallet_topup',topup,1000);
  RAISE EXCEPTION 'controlled reclaim interruption';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled reclaim interruption' THEN RAISE; END IF; END;
 IF (SELECT week_state FROM public.login_streaks WHERE user_id=u)<>'{}'::jsonb THEN RAISE EXCEPTION 'interruption persisted attendance'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',topup,1000);
 IF NOT (r->>'reclaimed')::boolean OR (r->>'day_offset')::integer<>key::integer OR (r->>'source_date')::date<>receipt_day THEN RAISE EXCEPTION 'receipt WAT day not used'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'wallet_topup',topup,1000);
 IF (r->>'reclaimed')::boolean OR NOT (r->>'already_reclaimed')::boolean THEN RAISE EXCEPTION 'replay counted twice'; END IF;
 -- A normal login merges its key, retaining the earlier receipt's attendance.
 r:=public.hg_mark_current_login_checkin(u);
 IF NOT (r->>'success')::boolean OR (SELECT week_state->>key FROM public.login_streaks WHERE user_id=u)<>'reclaimed'
 OR NOT ((SELECT week_state FROM public.login_streaks WHERE user_id=u) ? today_key) THEN RAISE EXCEPTION 'login overwrote reclamation'; END IF;
 before_state:=(SELECT week_state FROM public.login_streaks WHERE user_id=u);
 PERFORM public.hg_mark_current_login_checkin(u);
 IF (SELECT week_state FROM public.login_streaks WHERE user_id=u) IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'login replay changed attendance'; END IF;
 -- Reverse order is also safe: delivery must not overwrite a recorded login.
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,delivered_at,subtotal,total_amount,delivery_type)
 VALUES(food,u,c,'delivered','paid',now(),100,100,'off_campus'),(unpaid,u,c,'received','pending',NULL,100,100,'off_campus'),(addon_only,u,c,'delivered','paid',now(),100,100,'off_campus');
 INSERT INTO public.order_items(order_id,name_snapshot,price_snapshot,quantity,line_total,is_addon,campus_id)
 VALUES(food,'[AUDIT rollback] Food',100,1,100,false,c),(unpaid,'[AUDIT rollback] Unpaid food',100,1,100,false,c),(addon_only,'[AUDIT rollback] Addon',100,1,100,true,c);
 r:=public.hg_reclaim_login_checkin(u,'order',food,1000);
 IF (SELECT week_state FROM public.login_streaks WHERE user_id=u) IS DISTINCT FROM before_state THEN RAISE EXCEPTION 'delivery overwrote login'; END IF;
 UPDATE public.login_streaks SET week_state=week_state-today_key WHERE user_id=u;
 r:=public.hg_reclaim_login_checkin(u,'order',unpaid,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'unpaid delivery reclaimed'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'order',addon_only,1000);
 IF (r->>'reclaimed')::boolean THEN RAISE EXCEPTION 'addon-only order reclaimed'; END IF;
 r:=public.hg_reclaim_login_checkin(u,'order',food,1000);
 IF NOT (r->>'reclaimed')::boolean OR (r->>'day_offset')::integer<>today_key::integer THEN RAISE EXCEPTION 'paid food did not reclaim'; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=u)<>base_hp OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE user_id=u) THEN RAISE EXCEPTION 'attendance created HP'; END IF;
 IF has_function_privilege('authenticated','public.hg_reclaim_login_checkin(uuid,text,uuid,numeric)','EXECUTE')
 OR has_function_privilege('anon','public.hg_mark_current_login_checkin(uuid)','EXECUTE') THEN RAISE EXCEPTION 'public attendance mutation'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: source-receipt WAT date, threshold/owner/source/payment/food guards, old replay refusal, two-order attendance merge, interruption rollback, no HP creation and service-only access; all fixtures rolled back' AS evidence;
