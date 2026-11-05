BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); poor uuid:=gen_random_uuid(); cron_u uuid:=gen_random_uuid(); cron_ticket uuid;
 e uuid:=gen_random_uuid(); free_e uuid:=gen_random_uuid(); tier uuid:=gen_random_uuid(); promo uuid:=gen_random_uuid(); foreign_promo uuid:=gen_random_uuid();
 t uuid; t2 uuid; guest uuid; result jsonb; again jsonb; before_wallet numeric; before_hp integer; denied boolean;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Event finance','audit-event-finance-'||c),(other_c,'[AUDIT rollback] Other','audit-event-finance-'||other_c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-event-finance-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Event payer"}'),(poor,'audit-event-finance-'||poor||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='student',hp_balance=500 WHERE id=u;
 UPDATE public.profiles SET campus_id=c,role='student',hp_balance=0 WHERE id=poor;
 INSERT INTO public.wallets(user_id,balance,campus_id) VALUES(u,3000,c),(poor,0,c) ON CONFLICT(user_id) DO UPDATE SET balance=EXCLUDED.balance;
 UPDATE public.profiles SET wallet_balance=3000 WHERE id=u;
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,hp_per_attendee,location,capacity)
 VALUES(e,'[AUDIT rollback] Paid','audit-event-finance-'||e,now()-interval '1 hour',now()+interval '1 day',true,c,50,'FUTA',10),
 (free_e,'[AUDIT rollback] Free','audit-event-finance-'||free_e,now(),now()+interval '1 day',true,c,0,'FUTA',10);
 INSERT INTO public.feature_flags(feature_name,campus_id,is_active) VALUES('events',c,true),('hp_multiplier',c,false);
 INSERT INTO public.event_door_tokens(event_id,qr_token) VALUES(e,'audit-finance-door');
 INSERT INTO public.event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,price_hp,capacity,campus_id) VALUES(tier,e,'Audit tier',700,1000,50,5,c);
 INSERT INTO public.promo_codes(id,code,discount_type,discount_value,max_uses,max_uses_per_user,campus_id) VALUES(promo,'AUDIT-'||promo,'fixed',100,5,1,c),(foreign_promo,'AUDIT-'||foreign_promo,'fixed',900,5,1,other_c);
 result:=public.register_for_event_paid(e,u,tier,true,200,promo,'{"answers":{"meal":"rice"}}');
 IF result ? 'error' THEN RAISE EXCEPTION 'registration failed: %',result; END IF;
 t:=(result->>'ticket_id')::uuid;
 IF result->>'card_amount_used'<>'400.00' OR (SELECT balance FROM public.wallets WHERE user_id=u)<>2800 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>450 THEN RAISE EXCEPTION 'split/HP/promo reservation calculation incorrect: %',result; END IF;
 again:=public.register_for_event_paid(e,u,tier,true,200,promo,'{}');
 IF NOT (again->>'already_registered')::boolean OR again->>'ticket_id'<>t::text OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>1 THEN RAISE EXCEPTION 'registration replay duplicated reservation'; END IF;
 BEGIN PERFORM public.hg_admit_event_ticket(e,t,u,'audit-finance-door',c,50); RAISE EXCEPTION 'TEST unpaid admitted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 UPDATE public.event_tickets SET payment_expires_at=now()-interval '1 minute' WHERE id=t;
 BEGIN PERFORM public.hg_release_expired_event_reservation(t); RAISE EXCEPTION 'controlled interruption'; EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled interruption' THEN RAISE; END IF; END;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>2800 OR (SELECT payment_status FROM public.event_tickets WHERE id=t)<>'pending'
 OR EXISTS(SELECT 1 FROM public.wallet_transactions WHERE reference_type='event_ticket_expiry' AND reference_id=t) THEN RAISE EXCEPTION 'interrupted expiry left partial refund'; END IF;
 result:=public.hg_release_expired_event_reservation(t);
 IF NOT (result->>'expired')::boolean OR result->'receipt'->>'card_refunded'<>'0'
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>3000 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>500
 OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>0 OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0
 OR EXISTS(SELECT 1 FROM public.promo_code_uses WHERE ticket_id=t) THEN RAISE EXCEPTION 'expired reservation did not restore precisely'; END IF;
 IF (public.hg_release_expired_event_reservation(t)->>'expired')::boolean
 OR (SELECT count(*) FROM public.wallet_transactions WHERE reference_type='event_ticket_expiry' AND reference_id=t)<>1
 OR (SELECT count(*) FROM public.hp_transactions WHERE reference_type='event_ticket_expiry' AND reference_id=t AND type='adjustment')<>1
 OR EXISTS(SELECT 1 FROM public.monthly_hp_tracker WHERE user_id=u) THEN RAISE EXCEPTION 'expiry replay or earned-HP accounting incorrect'; END IF;
 result:=public.register_for_event_paid(e,u,tier,true,200,promo,'{}');
 IF result ? 'error' THEN RAISE EXCEPTION 'HP re-registration failed: %',result; END IF;
 t2:=(result->>'ticket_id')::uuid;
 IF t=t2 OR (SELECT count(*) FROM public.hp_transactions WHERE user_id=u AND source='event_registration')<>2 THEN RAISE EXCEPTION 're-registration reused old spend reference'; END IF;
 BEGIN PERFORM public.hg_mark_event_ticket_paid(t2,'paystack','AUDIT-EVENT-'||t2,399,'{}'); RAISE EXCEPTION 'TEST mismatched card accepted'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 PERFORM public.hg_mark_event_ticket_paid(t2,'paystack','AUDIT-EVENT-'||t2,400,'{}');
 PERFORM public.hg_mark_event_ticket_paid(t2,'paystack','AUDIT-EVENT-'||t2,400,'{}');
 IF (SELECT count(*) FROM public.payments WHERE ticket_id=t2)<>1 OR (SELECT payment_status FROM public.event_tickets WHERE id=t2)<>'paid' THEN RAISE EXCEPTION 'card confirmation replay incorrect'; END IF;
 UPDATE public.event_tickets SET payment_expires_at=now()-interval '1 minute' WHERE id=t2;
 IF (public.hg_release_expired_event_reservation(t2)->>'expired')::boolean THEN RAISE EXCEPTION 'paid ticket expired'; END IF;
 result:=public.hg_admit_event_ticket(e,t2,u,'audit-finance-door',c,50);
 IF result->>'hp_added_to_active'<>'50' THEN RAISE EXCEPTION 'paid admission did not credit event HP'; END IF;
 -- Foreign-campus promo and insufficient balances must undo all earlier seat mutations.
 result:=public.register_for_event_paid(e,poor,tier,false,0,foreign_promo,'{}');
 IF NOT (result ? 'error') OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>1 THEN RAISE EXCEPTION 'cross-campus promo accepted or leaked seat'; END IF;
 result:=public.register_for_event_paid(e,poor,tier,true,0,NULL,'{}');
 IF NOT (result ? 'error') OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>1 THEN RAISE EXCEPTION 'insufficient HP leaked seat'; END IF;
 result:=public.register_for_event_guest_paid(e,'Guest-Audit@Example.invalid','Audit guest','08012345678',tier,NULL,'{}');guest:=(result->>'ticket_id')::uuid;
 again:=public.register_for_event_guest_paid(e,'guest-audit@example.invalid','Audit guest','08012345678',tier,NULL,'{}');
 IF NOT (again->>'already_registered')::boolean OR again->>'ticket_id'<>guest::text THEN RAISE EXCEPTION 'guest email replay created duplicate: initial %, replay %',result,again; END IF;
 UPDATE public.event_tickets SET payment_expires_at=now()-interval '1 minute' WHERE id=guest;
 -- A new registration releases stale capacity before a cron sweep is due.
 result:=public.register_for_event_guest_paid(e,'next-audit@example.invalid','Next guest','08012345678',tier,NULL,'{}');
 IF result ? 'error' OR (SELECT payment_status FROM public.event_tickets WHERE id=guest)<>'expired'
 OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>2 THEN RAISE EXCEPTION 'guest stale capacity not released'; END IF;
 BEGIN PERFORM public.hg_mark_event_ticket_paid(guest,'paystack','AUDIT-LATE-'||guest,1000,'{}'); RAISE EXCEPTION 'TEST cancelled ticket revived'; EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE; END IF; END;
 result:=public.register_for_event_paid(free_e,poor,NULL,false,0,NULL,'{}');
 IF result->>'payment_status'<>'not_required' THEN RAISE EXCEPTION 'free registration regressed'; END IF;
 -- Guest promotions are campus-scoped and their per-email allowance spans events.
 result:=public.register_for_event_guest_paid(e,'foreign-promo@example.invalid','Audit guest','08012345678',tier,foreign_promo,'{}');
 IF NOT (result ? 'error') THEN RAISE EXCEPTION 'guest cross-campus promo accepted'; END IF;
 INSERT INTO public.event_ticket_tiers(event_id,name,price_naira,price_naira_full,campus_id) VALUES(free_e,'Later paid tier',1000,1000,c);
 result:=public.register_for_event_guest_paid(e,'guest-promo@example.invalid','Audit guest','08012345678',tier,promo,'{}');
 IF result ? 'error' THEN RAISE EXCEPTION 'valid guest promotion rejected: %',result; END IF;
 again:=public.register_for_event_guest_paid(free_e,'GUEST-PROMO@example.invalid','Audit guest','08012345678',
  (SELECT id FROM public.event_ticket_tiers WHERE event_id=free_e LIMIT 1),promo,'{}');
 IF NOT (again ? 'error') THEN RAISE EXCEPTION 'guest per-email promo limit bypassed'; END IF;
 -- Execute as the real pg_cron owner context: no request JWT, same credit guards.
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(cron_u,'audit-event-finance-'||cron_u||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,hp_balance=100 WHERE id=cron_u;
 INSERT INTO public.wallets(user_id,balance,campus_id) VALUES(cron_u,1000,c) ON CONFLICT(user_id) DO UPDATE SET balance=1000;
 result:=public.register_for_event_paid(e,cron_u,tier,true,200,NULL,'{}');
 cron_ticket:=(result->>'ticket_id')::uuid;
 IF cron_ticket IS NULL THEN RAISE EXCEPTION 'cron reservation failed: %',result; END IF;
 UPDATE public.event_tickets SET payment_expires_at=now()-interval '1 minute' WHERE id=cron_ticket;
 PERFORM set_config('request.jwt.claims','{}',true);
 PERFORM public.hg_expire_stale_event_tickets();
 IF current_setting('request.jwt.claims')<>'{}' OR (SELECT balance FROM public.wallets WHERE user_id=cron_u)<>1000
 OR (SELECT hp_balance FROM public.profiles WHERE id=cron_u)<>100 THEN RAISE EXCEPTION 'pg_cron refund context or claim restoration failed'; END IF;
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF has_function_privilege('anon','public.hg_release_expired_event_reservation(uuid)','execute') OR has_function_privilege('authenticated','public.hg_expire_stale_event_tickets()','execute') THEN RAISE EXCEPTION 'reservation recovery public'; END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: event split/HP/promo reservation, exact expiry returns, interruption/replay, rebooking, paid/card/guest/free admission, campus and balance guards; no provider call; all fixtures rolled back' AS evidence;
