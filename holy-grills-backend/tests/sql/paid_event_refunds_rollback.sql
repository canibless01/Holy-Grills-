BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid(); admin uuid:=gen_random_uuid(); outsider uuid:=gen_random_uuid(); u uuid:=gen_random_uuid(); attendee uuid:=gen_random_uuid();
 e uuid:=gen_random_uuid(); tier uuid:=gen_random_uuid(); promo uuid:=gen_random_uuid(); t uuid; checked_t uuid; guest uuid; req uuid:=gen_random_uuid(); guest_req uuid:=gen_random_uuid();
 r jsonb; again jsonb; claim jsonb; token uuid; v_review uuid:=gen_random_uuid(); denied boolean;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Refund','audit-ticket-refund-'||c),(other_c,'[AUDIT rollback] Other','audit-ticket-refund-'||other_c);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(admin,'audit-ticket-refund-'||admin||'@example.invalid','{}'),(outsider,'audit-ticket-refund-'||outsider||'@example.invalid','{}'),(u,'audit-ticket-refund-'||u||'@example.invalid','{}'),(attendee,'audit-ticket-refund-'||attendee||'@example.invalid','{}');
 UPDATE public.profiles SET campus_id=c,role='admin' WHERE id=admin;
 UPDATE public.profiles SET campus_id=other_c,role='admin' WHERE id=outsider;
 UPDATE public.profiles SET campus_id=c,role='student',hp_balance=500 WHERE id IN(u,attendee);
 INSERT INTO public.wallets(user_id,balance,campus_id) VALUES(u,3000,c),(attendee,3000,c) ON CONFLICT(user_id) DO UPDATE SET balance=3000;
 INSERT INTO public.events(id,title,slug,starts_at,ends_at,is_published,campus_id,location,capacity,hp_per_attendee) VALUES(e,'Refund test','audit-ticket-refund-'||e,now(),now()+interval '1 day',true,c,'FUTA',10,0);
 INSERT INTO public.feature_flags(feature_name,campus_id,is_active) VALUES('events',c,true),('hp_multiplier',c,false);
 INSERT INTO public.event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,price_hp,capacity,campus_id) VALUES(tier,e,'Paid',700,1000,50,10,c);
 INSERT INTO public.promo_codes(id,code,discount_type,discount_value,campus_id) VALUES(promo,'AUDIT-'||promo,'fixed',100,c);
 r:=public.hg_register_event_with_delivery(e,u,tier,true,200,promo,'{}');t:=(r->>'ticket_id')::uuid;
 PERFORM public.hg_pay_event_with_delivery(t,'paystack','AUDIT-REFUND-'||t,400,'{}');
 INSERT INTO public.redemption_cost_log(event_ticket_id,user_id,reward_type,hp_spent,actual_cost,campus_id) VALUES(t,u,'event',50,300,c);
 denied:=false;BEGIN PERFORM public.hg_request_event_ticket_refund(outsider,e,t,req,'Customer requests refund');EXCEPTION WHEN insufficient_privilege THEN denied:=true;END;
 IF NOT denied THEN RAISE EXCEPTION 'foreign admin refunded ticket';END IF;
 denied:=false;BEGIN PERFORM public.hg_request_event_ticket_refund(u,e,t,req,'Customer requests refund');EXCEPTION WHEN insufficient_privilege THEN denied:=true;END;
 IF NOT denied THEN RAISE EXCEPTION 'student refunded ticket';END IF;
 BEGIN PERFORM public.hg_request_event_ticket_refund(admin,e,t,req,'Customer requests refund');RAISE EXCEPTION 'controlled interruption';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'controlled interruption' THEN RAISE;END IF;END;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>2800 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>450 OR EXISTS(SELECT 1 FROM hg_internal.event_ticket_refunds WHERE ticket_id=t)
 OR (SELECT actual_cost FROM public.redemption_cost_log WHERE event_ticket_id=t)<>300 THEN RAISE EXCEPTION 'interrupted refund left partial financial state'; END IF;
 r:=public.hg_request_event_ticket_refund(admin,e,t,req,'Customer requests refund');
 IF r->>'destination'<>'wallet' OR r->>'state'<>'completed' OR (r->>'amount')::numeric<>600 OR (r->>'hp_returned')::integer<>50
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>3400 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>500 THEN RAISE EXCEPTION 'member split refund amount/HP incorrect: %',r;END IF;
 IF (SELECT payment_status FROM public.event_tickets WHERE id=t)<>'refunded' OR (SELECT sold_count FROM public.event_ticket_tiers WHERE id=tier)<>0
 OR (SELECT used_count FROM public.promo_codes WHERE id=promo)<>0 OR (SELECT actual_cost FROM public.redemption_cost_log WHERE event_ticket_id=t)<>0 THEN RAISE EXCEPTION 'refund did not release ticket, promo, seat or cost';END IF;
 again:=public.hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Another duplicate request');
 IF NOT (again->>'idempotent')::boolean OR (SELECT count(*) FROM public.wallet_transactions WHERE reference_type='event_ticket_refund' AND reference_id=t)<>1
 OR (SELECT count(*) FROM public.hp_transactions WHERE reference_type='event_ticket_refund' AND reference_id=t)<>1 THEN RAISE EXCEPTION 'member refund repeated financial credit';END IF;
 claim:=public.hg_claim_event_refund(req);
 IF claim->>'state'<>'completed' OR (claim->>'notified')::boolean THEN RAISE EXCEPTION 'member refund notice missing';END IF;
 PERFORM public.hg_ack_event_refund_notice(req);
 IF NOT (SELECT notified FROM hg_internal.event_ticket_refunds WHERE id=req) THEN RAISE EXCEPTION 'notice ack failed';END IF;
 -- A registered and paid attendee who has entered cannot be refunded.
 r:=public.hg_register_event_with_delivery(e,attendee,tier,false,1000,NULL,'{}');checked_t:=(r->>'ticket_id')::uuid;
 PERFORM public.hg_admit_event_ticket(e,checked_t,admin,NULL,c,0);
 BEGIN PERFORM public.hg_request_event_ticket_refund(admin,e,checked_t,gen_random_uuid(),'Customer requests refund');RAISE EXCEPTION 'TEST checked-in ticket refunded';EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE;END IF;END;
 r:=public.hg_register_guest_event_with_delivery(e,'guest-refund@example.invalid','Guest','08012345678',tier,NULL,'{}');guest:=(r->>'ticket_id')::uuid;
 PERFORM public.hg_pay_event_with_delivery(guest,'paystack','AUDIT-GUEST-'||guest,1000,'{}');
 r:=public.hg_request_event_ticket_refund(admin,e,guest,guest_req,'Guest requests refund');
 IF r->>'destination'<>'paystack' OR r->>'state'<>'queued' OR (SELECT payment_status FROM public.event_tickets WHERE id=guest)<>'refund_pending'
 OR EXISTS(SELECT 1 FROM public.notification_deliveries WHERE id=guest_req) THEN RAISE EXCEPTION 'guest refund falsely complete or mailed early';END IF;
 BEGIN PERFORM public.hg_admit_event_ticket(e,guest,admin,NULL,c,0);RAISE EXCEPTION 'TEST refund-pending guest admitted';EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE;END IF;END;
 claim:=public.hg_claim_event_refund(guest_req);token:=(claim->>'token')::uuid;
 IF claim->>'state'<>'claimed' OR public.hg_claim_event_refund(guest_req)->>'state'<>'busy' THEN RAISE EXCEPTION 'guest claim not exclusive';END IF;
 IF public.hg_begin_event_refund(guest_req,gen_random_uuid()) THEN RAISE EXCEPTION 'stale refund token began handoff';END IF;
 PERFORM public.hg_begin_event_refund(guest_req,token);
 UPDATE hg_internal.event_ticket_refunds SET lease_until=now()-interval '1 minute' WHERE id=guest_req;
 IF public.hg_claim_event_refund(guest_req)->>'state'<>'uncertain' THEN RAISE EXCEPTION 'ambiguous refund automatically retried';END IF;
 denied:=false;BEGIN PERFORM public.hg_review_event_refund(outsider,e,guest_req,v_review,'lookup','123','Paystack dashboard confirms refund 123');EXCEPTION WHEN insufficient_privilege THEN denied:=true;END;
 IF NOT denied THEN RAISE EXCEPTION 'foreign refund review';END IF;
 r:=public.hg_review_event_refund(admin,e,guest_req,v_review,'lookup','123','Paystack dashboard confirms refund 123');
 again:=public.hg_review_event_refund(admin,e,guest_req,v_review,'lookup','123','Paystack dashboard confirms refund 123');
 IF NOT (again->>'idempotent')::boolean OR r->>'state'<>'processing' THEN RAISE EXCEPTION 'refund review replay changed intent';END IF;
 claim:=public.hg_claim_event_refund(guest_req);token:=(claim->>'token')::uuid;
 IF claim->>'state'<>'checking' OR claim->>'provider_refund_id'<>'123' THEN RAISE EXCEPTION 'refund lookup would create a new request';END IF;
 BEGIN PERFORM public.hg_finish_event_refund(guest_req,token,'completed','999',NULL);RAISE EXCEPTION 'TEST wrong refund ID completed';EXCEPTION WHEN raise_exception THEN IF SQLERRM LIKE 'TEST%' THEN RAISE;END IF;END;
 PERFORM public.hg_finish_event_refund(guest_req,token,'processing','123',NULL);
 IF public.hg_claim_event_refund(guest_req)->>'state'<>'deferred' THEN RAISE EXCEPTION 'provider poll backoff ignored';END IF;
 UPDATE hg_internal.event_ticket_refunds SET next_at=now()-interval '1 minute' WHERE id=guest_req;
 claim:=public.hg_claim_event_refund(guest_req);token:=(claim->>'token')::uuid;
 PERFORM public.hg_finish_event_refund(guest_req,token,'completed','123',NULL);
 IF (SELECT payment_status FROM public.event_tickets WHERE id=guest)<>'refunded' OR (SELECT count(*) FROM public.notification_deliveries WHERE id=guest_req AND dispatch_payload->>'kind'='event_refund_email')<>1 THEN RAISE EXCEPTION 'processed refund receipt/mail missing';END IF;
 IF public.hg_finish_event_refund(guest_req,token,'completed','123',NULL) THEN RAISE EXCEPTION 'completed refund re-finished';END IF;
 IF jsonb_array_length(public.hg_event_refund_list(admin,e))<>2 THEN RAISE EXCEPTION 'scoped history missing refunds';END IF;
 -- Wallet-only and HP-only paid variants use the same conservation boundary.
 r:=public.hg_register_event_with_delivery(e,u,tier,false,1000,NULL,'{}');t:=(r->>'ticket_id')::uuid;
 PERFORM public.hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Wallet-only cancellation before entry');
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>3400 THEN RAISE EXCEPTION 'wallet-only refund did not conserve balance';END IF;
 INSERT INTO public.event_ticket_tiers(event_id,name,price_naira,price_naira_full,price_hp,capacity,campus_id) VALUES(e,'HP discount to zero',0,1000,25,10,c) RETURNING id INTO tier;
 r:=public.hg_register_event_with_delivery(e,u,tier,true,0,NULL,'{}');t:=(r->>'ticket_id')::uuid;
 r:=public.hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'HP-only cancellation before entry');
 IF (r->>'amount')::numeric<>0 OR (SELECT hp_balance FROM public.profiles WHERE id=u)<>500 OR EXISTS(SELECT 1 FROM public.wallet_transactions WHERE reference_type='event_ticket_refund' AND reference_id=t) THEN RAISE EXCEPTION 'HP-only refund invented money or lost points';END IF;
 -- A pre-handoff crash recovers safely; a completed POST uncertainty does not.
 INSERT INTO public.event_ticket_tiers(event_id,name,price_naira,price_naira_full,capacity,campus_id) VALUES(e,'Second cash tier',1000,1000,10,c) RETURNING id INTO tier;
 r:=public.hg_register_guest_event_with_delivery(e,'second-guest-refund@example.invalid','Second guest','08012345678',tier,NULL,'{}');t:=(r->>'ticket_id')::uuid;
 PERFORM public.hg_pay_event_with_delivery(t,'paystack','AUDIT-SECOND-'||t,1000,'{}');
 r:=public.hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Guest cancellation before entry');req:=(r->>'id')::uuid;
 claim:=public.hg_claim_event_refund(req);token:=(claim->>'token')::uuid;
 UPDATE hg_internal.event_ticket_refunds SET lease_until=now()-interval '1 minute' WHERE id=req;
 again:=public.hg_claim_event_refund(req);
 IF again->>'state'<>'claimed' OR again->>'token'=token::text OR public.hg_begin_event_refund(req,token) THEN RAISE EXCEPTION 'pre-handoff claim recovery failed';END IF;
 PERFORM public.hg_finish_event_refund(req,(again->>'token')::uuid,'failed',NULL,'Known provider rejection');
 r:=public.hg_review_event_refund(admin,e,req,gen_random_uuid(),'not_sent',NULL,'Paystack confirms no refund was created');
 IF r->>'state'<>'queued' OR public.hg_claim_event_refund(req)->>'state'<>'claimed' THEN RAISE EXCEPTION 'confirmed no-send review did not requeue';END IF;
 -- New money work must not wait behind an old provider-processing poll.
 UPDATE hg_internal.event_ticket_refunds SET state='queued',next_at=now(),lease_until=NULL,token=NULL WHERE id=req;
 UPDATE hg_internal.event_ticket_refunds SET state='processing',next_at=now()-interval '1 hour',created_at=now()-interval '1 day' WHERE id=guest_req;
 IF public.hg_due_event_refunds(1)->>0<>req::text THEN RAISE EXCEPTION 'provider polling starved newly queued refund';END IF;
 IF has_table_privilege('authenticated','hg_internal.event_ticket_refunds','select') OR has_table_privilege('anon','public.event_tickets','update')
 OR has_function_privilege('authenticated','public.hg_request_event_ticket_refund(uuid,uuid,uuid,uuid,text)','execute') THEN RAISE EXCEPTION 'refund financial data or mutation publicly accessible';END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: member wallet/HP full refund, promo/seat/cost restoration, interruption/replay, role/campus/check-in guards, guest reservation/lease/uncertainty/provider review/completion/mail, polling and private grants; all fixtures rolled back' AS evidence;
