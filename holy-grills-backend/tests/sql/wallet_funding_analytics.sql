-- Exact amounts, policy exclusions, scheduling boundaries and roles; rollback all fixtures.
BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.wa_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Wallet analytics check: %',label; END IF; END$$;
CREATE FUNCTION pg_temp.wa_error(statement text,expected text) RETURNS void LANGUAGE plpgsql AS $$BEGIN
 BEGIN EXECUTE statement;EXCEPTION WHEN OTHERS THEN IF SQLERRM=expected THEN RETURN;END IF;RAISE;END;
 RAISE EXCEPTION 'Expected wallet analytics error: %',expected;
END$$;
CREATE FUNCTION pg_temp.wa_person(c uuid,r text DEFAULT 'student',balance numeric DEFAULT 0,active boolean DEFAULT true) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE u uuid:=gen_random_uuid();BEGIN
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-wa-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Wallet analytics"}');
 UPDATE profiles SET campus_id=c,is_active=active,role=(jsonb_populate_record(NULL::public.profiles,jsonb_build_object('role',r))).role WHERE id=u;
 INSERT INTO wallets(user_id,balance,currency,campus_id) VALUES(u,balance,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,currency='NGN',campus_id=c;
 RETURN u;
END$$;
CREATE FUNCTION pg_temp.wa_plan(c uuid,state text,amount integer,frequency integer DEFAULT 1,successful integer DEFAULT 1,stop integer DEFAULT NULL,
 ends timestamptz DEFAULT NULL,due timestamptz DEFAULT now(),active boolean DEFAULT true,owner_role text DEFAULT 'student',card boolean DEFAULT true,pending text DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql AS $$DECLARE u uuid;id uuid:=gen_random_uuid();BEGIN
 u:=pg_temp.wa_person(c,owner_role,0,active);
 INSERT INTO hg_internal.wallet_funding_plans(id,user_id,campus_id,amount_kobo,interval_days,stop_after,end_at,state,consent_version,authorization_email,card_authorization,setup_reference,successful_payments,total_credited_kobo,next_due_at)
 VALUES(id,u,c,amount,frequency,stop,ends,state,'wallet-auto-funding-v2','do-not-return@example.invalid',CASE WHEN card THEN '{"authorization_code":"AUTH_NEVER_RETURN","reusable":true,"channel":"card"}'::jsonb ELSE NULL END,'AUDIT-REPORT-'||id,successful,successful::bigint*amount,due);
 IF pending IS NOT NULL THEN
 INSERT INTO hg_internal.wallet_funding_attempts(plan_id,cycle,reference,state,scheduled_for) VALUES(id,successful+1,'AUDIT-PENDING-'||id,pending,due);
 END IF;
 RETURN id;
END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();sa uuid;admin_id uuid;student uuid;inactive uuid;other_user uuid;manager uuid;
 p1 uuid;p2 uuid;p3 uuid;p4 uuid;p uuid;super_plan uuid;other_plan uuid;tx uuid:=gen_random_uuid();super_tx uuid:=gen_random_uuid();transfer uuid:=gen_random_uuid();
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;start_at timestamptz;end_at timestamptz;r jsonb;g jsonb;h jsonb;baseline_global jsonb;prior_count bigint;
BEGIN
 start_at:=(today-2)::timestamp AT TIME ZONE 'Africa/Lagos';end_at:=(today+1)::timestamp AT TIME ZONE 'Africa/Lagos';
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Wallet funding','audit-wa-'||c),(other_c,'[AUDIT rollback] Other funding','audit-wa-'||other_c);
 sa:=pg_temp.wa_person(c,'super_admin',999999);baseline_global:=hg_wallet_funding_analytics(sa,NULL,today-2,today);admin_id:=pg_temp.wa_person(c,'admin',40);student:=pg_temp.wa_person(c,'student',500.50);
 inactive:=pg_temp.wa_person(c,'student',100.25,false);other_user:=pg_temp.wa_person(other_c,'student',700);manager:=pg_temp.wa_person(c,'community_manager');
 -- Four eligible schedules: 600 + 200 + 100 + (300/1000/3000) across 7/30/90 days.
 p1:=pg_temp.wa_plan(c,'active',20000,2,1,4);
 p2:=pg_temp.wa_plan(c,'active',10000,1,1,NULL,now()+interval '2 days');
 p3:=pg_temp.wa_plan(c,'active',10000,1,1,2,NULL,now()-interval '3 days');
 p4:=pg_temp.wa_plan(c,'active',10000,3);
 PERFORM pg_temp.wa_plan(c,'active',100000,1,1,NULL,NULL,now(),false);
 p:=pg_temp.wa_plan(c,'active',100000);UPDATE profiles SET campus_id=other_c WHERE id=(SELECT user_id FROM hg_internal.wallet_funding_plans WHERE id=p);
 PERFORM pg_temp.wa_plan(c,'active',100000,1,1,NULL,NULL,now(),true,'student',false);
 PERFORM pg_temp.wa_plan(c,'active',30000,1,1,NULL,NULL,now(),true,'student',true,'handed_off');
 PERFORM pg_temp.wa_plan(c,'active',100000,1,1,NULL,now()-interval '1 hour');
 PERFORM pg_temp.wa_plan(c,'active',100000,1,2,2);
 PERFORM pg_temp.wa_plan(c,'draft',100000,1,0,NULL,NULL,now(),true,'student',false,'setup');
 p:=pg_temp.wa_plan(c,'attention',100000);
 INSERT INTO hg_internal.wallet_funding_attempts(plan_id,cycle,reference,state,scheduled_for,updated_at) VALUES(p,2,'AUDIT-FAILED-'||p,'failed',now(),now());
 PERFORM pg_temp.wa_plan(c,'stopped',100000);PERFORM pg_temp.wa_plan(c,'completed',100000);
 super_plan:=pg_temp.wa_plan(c,'active',100000000,1,1,NULL,NULL,now(),true,'super_admin');
 other_plan:=pg_temp.wa_plan(other_c,'active',50000,1,1,2);
 INSERT INTO wallet_transactions(id,user_id,type,amount,balance_after,reference_type,provider,campus_id,created_at) VALUES
 (gen_random_uuid(),student,'credit',1000,0,'topup','paystack',c,start_at),
 (tx,(SELECT user_id FROM hg_internal.wallet_funding_plans WHERE id=p1),'credit',200,200,'topup','paystack',c,start_at+interval '12 hours'),
 (gen_random_uuid(),student,'credit',50,0,'refund','internal-refund',c,start_at+interval '1 day'),
 (gen_random_uuid(),student,'debit',100,0,'order',NULL,c,start_at+interval '1 day'),
 (gen_random_uuid(),student,'credit',25,0,'admin_grant',NULL,c,start_at+interval '1 day'),
 (super_tx,(SELECT user_id FROM hg_internal.wallet_funding_plans WHERE id=super_plan),'credit',1000000,0,'topup','paystack',c,start_at),
 (gen_random_uuid(),other_user,'credit',700,700,'topup','paystack',other_c,start_at),
 (gen_random_uuid(),student,'credit',9999,0,'topup','paystack',c,start_at-interval '1 second'),
 (gen_random_uuid(),student,'credit',7000,0,'topup','paystack',c,end_at);
 INSERT INTO hg_internal.wallet_funding_attempts(plan_id,cycle,reference,state,scheduled_for,transaction_id) VALUES
 (p1,1,'AUDIT-SUCCESS-'||p1,'succeeded',start_at,tx),(super_plan,1,'AUDIT-SUCCESS-'||super_plan,'succeeded',start_at,super_tx);
 INSERT INTO hg_internal.wallet_transfers(id,sender_id,recipient_id,campus_id,amount_kobo,sender_name,recipient_name,sender_code,recipient_code,sender_balance_after,recipient_balance_after,created_at)
 VALUES(transfer,student,admin_id,c,5000,'Audit sender','Audit recipient','AUDIT1','AUDIT2',500.50,40,start_at),
 (gen_random_uuid(),sa,student,c,99999900,'Excluded test sender','Audit recipient','SUPER','AUDIT1',0,500.50,start_at);
 INSERT INTO wallet_transactions(user_id,type,amount,balance_after,reference_type,reference_id,provider,campus_id,created_at) VALUES
 (student,'debit',50,500.50,'wallet_transfer',transfer,'internal',c,start_at),(admin_id,'credit',50,40,'wallet_transfer',transfer,'internal',c,start_at),
 (student,'credit',999999,500.50,'wallet_transfer',NULL,'internal',c,start_at);
 SELECT count(*) INTO prior_count FROM hg_internal.wallet_funding_attempts;
 r:=hg_wallet_funding_analytics(sa,c,today-2,today);
 PERFORM pg_temp.wa_check((r#>>'{balances,outstanding}')::numeric=640.75,'customer credit excludes super-admin funds; includes non-super staff and inactive balances');
 PERFORM pg_temp.wa_check((r#>>'{balances,inactive_balance}')::numeric=100.25 AND (r#>>'{balances,funded_accounts}')::int=3,'inactive balances and funded user count');
 PERFORM pg_temp.wa_check((r#>>'{activity,funding_received}')::numeric=1200 AND (r#>>'{activity,automatic_received}')::numeric=200 AND (r#>>'{activity,manual_funding_received}')::numeric=1000,'actual confirmed funding; no super-admin, transfer, refund or outside-date inflation');
 PERFORM pg_temp.wa_check((r#>>'{activity,refunds_credited}')::numeric=50 AND (r#>>'{activity,other_credits}')::numeric=25 AND (r#>>'{activity,wallet_debits}')::numeric=100,'refund, other credit and debit categories');
 PERFORM pg_temp.wa_check((r#>>'{transfers,count}')::int=1 AND (r#>>'{transfers,volume}')::numeric=50,'internal transfers counted once; super-admin transfers excluded');
 PERFORM pg_temp.wa_check((r#>>'{automatic_funding,plans}')::int=14 AND (r#>>'{automatic_funding,states,active}')::int=10,'plan counts exclude super-admin and another campus');
 PERFORM pg_temp.wa_check((r#>>'{projection,eligible_plans}')::int=4 AND (r#>>'{projection,excluded_active_plans}')::int=6,'eligibility excludes unavailable owners/cards, expired/exhausted and in-flight plans');
 PERFORM pg_temp.wa_check((r#>>'{projection,horizons,0,amount}')::numeric=1200 AND (r#>>'{projection,horizons,1,amount}')::numeric=1900 AND (r#>>'{projection,horizons,2,amount}')::numeric=3900,'7/30/90-day forecast respects frequency, caps, end times and no overdue burst');
 PERFORM pg_temp.wa_check((r#>>'{projection,daily,0,amount}')::numeric=500,'today only one overdue contribution; exact calendar bucket');
 PERFORM pg_temp.wa_check((r#>>'{payment_health,awaiting_confirmation}')::int=1 AND (r#>>'{payment_health,unconfirmed_amount}')::numeric=300 AND (r#>>'{payment_health,awaiting_first_payment}')::int=1 AND (r#>>'{payment_health,failed_in_period}')::int=1,'unconfirmed/draft/failed payment health distinct from receipts');
 PERFORM pg_temp.wa_check((r#>>'{daily_history,0,manual_funding}')::numeric=1000 AND (r#>>'{daily_history,0,automatic_funding}')::numeric=200 AND jsonb_array_length(r->'daily_history')=3,'WAT midnight boundaries and complete daily history');
 PERFORM pg_temp.wa_check(position('AUTH_NEVER_RETURN' in r::text)=0 AND position('authorization_email' in r::text)=0 AND position('card_authorization' in r::text)=0,'no card credentials or private funding details');
 PERFORM pg_temp.wa_check((SELECT count(*) FROM hg_internal.wallet_funding_attempts)=prior_count AND (SELECT state FROM hg_internal.wallet_funding_plans WHERE id=p3)='active','report does not dispatch, reconcile or mutate plans');
 g:=hg_wallet_funding_analytics(sa,NULL,today-2,today);
 PERFORM pg_temp.wa_check((g#>>'{balances,outstanding}')::numeric=(baseline_global#>>'{balances,outstanding}')::numeric+1340.75 AND (g#>>'{activity,funding_received}')::numeric=(baseline_global#>>'{activity,funding_received}')::numeric+1900 AND (g#>>'{projection,horizons,0,amount}')::numeric=(baseline_global#>>'{projection,horizons,0,amount}')::numeric+1700,'global scope adds genuine other-campus money only');
 g:=hg_wallet_funding_analytics(admin_id,NULL,today-2,today);
 PERFORM pg_temp.wa_check((g#>>'{balances,outstanding}')::numeric=640.75 AND g->>'campus_id'=c::text,'campus admin pinned to own campus');
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,%L,%L,%L)',admin_id,other_c,today-2,today),'wallet_analytics_forbidden');
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,NULL,%L,%L)',student,today-2,today),'wallet_analytics_forbidden');
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,NULL,%L,%L)',manager,today-2,today),'wallet_analytics_forbidden');
 UPDATE profiles SET is_active=false WHERE id=admin_id;
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,NULL,%L,%L)',admin_id,today-2,today),'wallet_analytics_forbidden');
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,NULL,%L,%L)',sa,today,today-1),'wallet_analytics_date_invalid');
 PERFORM pg_temp.wa_error(format('SELECT hg_wallet_funding_analytics(%L,NULL,%L,%L)',sa,today-366,today),'wallet_analytics_date_invalid');
 PERFORM pg_temp.wa_check(NOT has_function_privilege('anon','public.hg_wallet_funding_analytics(uuid,uuid,date,date)','EXECUTE') AND NOT has_function_privilege('authenticated','public.hg_wallet_funding_analytics(uuid,uuid,date,date)','EXECUTE'),'helper service-only');
 PERFORM pg_temp.wa_check((SELECT provolatile='s' FROM pg_proc WHERE oid='public.hg_wallet_funding_analytics(uuid,uuid,date,date)'::regprocedure),'read-only stable snapshot');
END $test$;
ROLLBACK;
