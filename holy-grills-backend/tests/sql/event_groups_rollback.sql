-- Synthetic event, people and receipts only; all changes roll back. No provider calls.
BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $test$
DECLARE c uuid:=gen_random_uuid(); buyer uuid:=gen_random_uuid(); admin uuid:=gen_random_uuid();
 e uuid:=gen_random_uuid(); tier1 uuid:=gen_random_uuid();tier2 uuid:=gen_random_uuid();
 organizer uuid:=gen_random_uuid();post_attendee uuid:=gen_random_uuid();attendee uuid:=gen_random_uuid();recipient uuid:=gen_random_uuid();guest_buyer uuid:=gen_random_uuid();
 claim_attendee integer;claim_buyer integer;claim_replay integer;
 g jsonb; again jsonb; t uuid; r jsonb; grp uuid; before_balance numeric; i integer;
 contact jsonb; roster jsonb; emails text[]; reference text;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Group tickets','audit-group-'||c);
 INSERT INTO auth.users(id,email,raw_user_meta_data,email_confirmed_at) VALUES(buyer,'group-buyer-'||buyer||'@example.invalid','{}',now()),(admin,'group-admin-'||admin||'@example.invalid','{}',now());
 INSERT INTO public.profiles(id,email) VALUES(buyer,'group-buyer-'||buyer||'@example.invalid'),(admin,'group-admin-'||admin||'@example.invalid') ON CONFLICT(id) DO NOTHING;
 UPDATE public.profiles SET campus_id=c,role='student',is_active=true WHERE id=buyer;
 UPDATE public.profiles SET campus_id=c,role='admin',is_active=true WHERE id=admin;
 INSERT INTO auth.users(id,email,raw_user_meta_data,email_confirmed_at) VALUES(organizer,'organizer-'||organizer||'@example.invalid','{}',now());
 UPDATE profiles SET campus_id=c,role='event_organizer',is_active=true WHERE id=organizer;
 INSERT INTO public.wallets(user_id,balance) VALUES(buyer,1000) ON CONFLICT(user_id) DO UPDATE SET balance=1000;
 INSERT INTO public.feature_flags(feature_name,is_active,campus_id) VALUES('events',true,c),('hp_multiplier',false,c);
 INSERT INTO public.events(id,title,slug,location,starts_at,ends_at,capacity,is_published,is_paid,campus_id,hp_per_attendee)
 VALUES(e,'[AUDIT rollback] Group tickets','audit-group-'||e,'Rollback venue',now()+interval '5 minutes',now()+interval '2 hours',30,true,true,c,50);
 INSERT INTO public.event_ticket_tiers(id,event_id,name,price_naira,price_naira_full,price_hp,capacity,campus_id)
 VALUES(tier1,e,'First',80,100,10,20,c),(tier2,e,'Second',160,200,20,20,c);
 PERFORM hg_review_organizer_event(admin,e,'configure',jsonb_build_object('organizer_id',organizer,'tiers',jsonb_build_array(jsonb_build_object('id',tier1,'organizer_amount',70),jsonb_build_object('id',tier2,'organizer_amount',140))));
 PERFORM hg_review_organizer_event(admin,e,'approve');
 contact:=jsonb_build_object('name','Buyer','email','group-buyer-'||buyer||'@example.invalid','phone','08012345678');
 roster:=jsonb_build_array(jsonb_build_object('name','First attendee','email','audit-group-a-'||e||'@example.invalid','phone','08012345678','tier_id',tier1,'answers',jsonb_build_object('department','Computing')),
 jsonb_build_object('name','Second attendee','email','audit-group-b-'||e||'@example.invalid','phone','08012345678','tier_id',tier2,'answers',jsonb_build_object('department','Engineering')));
 g:=public.hg_create_event_group(e,buyer,contact,roster,'wallet',0,NULL,'wallet-group-'||e,repeat('a',64));grp:=(g->>'id')::uuid;
 IF g->>'payment_status'<>'paid' OR (g->>'total')::numeric<>300 OR (SELECT balance FROM wallets WHERE user_id=buyer)<>700
 OR (SELECT count(*) FROM event_tickets WHERE group_id=grp AND status='confirmed' AND user_id IS NULL)<>2
 OR (SELECT count(DISTINCT qr_code) FROM event_tickets WHERE group_id=grp)<>2 THEN RAISE EXCEPTION 'wallet group admission/conservation failed: %',g;END IF;
 IF (hg_organizer_event_balance(organizer,e)->>'earned')::numeric<>210 THEN RAISE EXCEPTION 'group settlement used buyer/aggregate listing rather than each tier payout';END IF;
 again:=public.hg_create_event_group(e,buyer,contact,roster,'wallet',0,NULL,'wallet-group-'||e,repeat('a',64));
 IF again->>'id'<>g->>'id' OR (SELECT balance FROM wallets WHERE user_id=buyer)<>700 THEN RAISE EXCEPTION 'replayed group charged again';END IF;
 BEGIN
  PERFORM public.hg_create_event_group(e,buyer,contact,roster,'wallet',0,NULL,'wallet-group-'||e,repeat('b',64));RAISE EXCEPTION 'conflicting intent accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_GROUP_INTENT_CONFLICT' THEN RAISE;END IF;END;
 -- A different intent must reject existing attendees, not reveal/adopt their tickets.
 BEGIN
  PERFORM public.hg_create_event_group(e,buyer,contact,roster,'wallet',0,NULL,'duplicate-group-'||e,repeat('b',64));RAISE EXCEPTION 'existing attendee charged again';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_GROUP_ATTENDEE_REGISTERED' THEN RAISE;END IF;END;
 IF (SELECT count(*) FROM hg_internal.event_ticket_groups WHERE event_id=e)<>1 THEN RAISE EXCEPTION 'failed group left partial booking';END IF;
 -- Changed pricing must roll back all provisional reservations and counters.
 BEGIN
  PERFORM hg_create_event_group(e,buyer,contact||jsonb_build_object('_expected_subtotal','299'),replace(roster::text,'audit-group-','audit-price-group-')::jsonb,'wallet',0,NULL,'price-group-'||e,repeat('f',64));
  RAISE EXCEPTION 'unreviewed price accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_GROUP_PRICE_CHANGED' THEN RAISE;END IF;END;
 IF (SELECT count(*) FROM hg_internal.event_ticket_groups WHERE event_id=e)<>1 OR (SELECT balance FROM wallets WHERE user_id=buyer)<>700 THEN RAISE EXCEPTION 'price change leaked reservations/debit';END IF;
 -- Refund a group wallet ticket to the buyer, not the attendee.
 SELECT id INTO t FROM event_tickets WHERE group_id=grp AND tier_id=tier1;
 r:=public.hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Support-approved group ticket cancellation');
 IF r->>'state'<>'completed' OR (SELECT balance FROM wallets WHERE user_id=buyer)<>800
 OR (SELECT user_id FROM event_tickets WHERE id=t) IS NOT NULL THEN RAISE EXCEPTION 'group wallet refund ownership failed: %',r;END IF;
 -- Paid card group uses ONE provider reference, allocated receipts per attendee.
 roster:=replace(roster::text,'audit-group-a-','audit-group-card-a-')::jsonb;
 roster:=replace(roster::text,'audit-group-b-','audit-group-card-b-')::jsonb;
 g:=public.hg_create_event_group(e,buyer,contact,roster,'card',0,NULL,'card-group-'||e,repeat('c',64));grp:=(g->>'id')::uuid;reference:=g->>'payment_reference';
 IF (SELECT count(*) FROM event_tickets WHERE group_id=grp AND status='pending_payment')<>2 THEN RAISE EXCEPTION 'unpaid group issued entry';END IF;
 BEGIN
  PERFORM hg_pay_event_group(grp,reference,299,'{}');RAISE EXCEPTION 'wrong amount accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_GROUP_PAYMENT_MISMATCH' THEN RAISE;END IF;END;
 g:=hg_pay_event_group(grp,reference,300,'{}');again:=hg_pay_event_group(grp,reference,300,'{}');
 IF (SELECT count(*) FROM event_tickets WHERE group_id=grp AND payment_status='paid' AND status='confirmed')<>2
 OR (SELECT sum(p.amount) FROM payments p JOIN event_tickets et ON et.id=p.ticket_id WHERE et.group_id=grp)<>300
 OR (SELECT count(*) FROM payments p JOIN event_tickets et ON et.id=p.ticket_id WHERE et.group_id=grp)<>2 THEN RAISE EXCEPTION 'group payment fanout/replay failed';END IF;
 -- Verified recipients own attendance HP; the purchaser owns any money refund.
 SELECT id INTO t FROM event_tickets WHERE group_id=grp AND tier_id=tier1;
 INSERT INTO auth.users(id,email,raw_user_meta_data,email_confirmed_at)
 VALUES(attendee,(roster->0->>'email'),'{}',now()),(recipient,(roster->1->>'email'),'{}',now());
 UPDATE profiles SET campus_id=c,is_active=true WHERE id IN(attendee,recipient);
 PERFORM hg_link_verified_event_tickets(attendee);PERFORM hg_link_verified_event_tickets(recipient);
 IF (SELECT user_id FROM event_tickets WHERE id=t) IS DISTINCT FROM attendee THEN RAISE EXCEPTION 'group recipient not linked to verified identity';END IF;
 r:=hg_admit_event_ticket(e,t,admin,NULL,c,50);again:=hg_admit_event_ticket(e,t,admin,NULL,c,50);
 IF (r->>'hp_added_to_active')::integer<>50 OR NOT (again->>'replayed')::boolean
 OR (SELECT count(*) FROM hp_transactions WHERE user_id=attendee AND reference_type='event' AND reference_id=e AND amount=50)<>1
 OR EXISTS(SELECT 1 FROM hp_transactions WHERE user_id=buyer AND reference_type='event' AND reference_id=e)
 THEN RAISE EXCEPTION 'attendance HP recipient/replay failed: %, %',r,again;END IF;
 SELECT id INTO t FROM event_tickets WHERE group_id=grp AND tier_id=tier2;
 SELECT balance INTO before_balance FROM wallets WHERE user_id=buyer;
 r:=hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Support approved unused group attendee refund');
 IF (SELECT balance FROM wallets WHERE user_id=buyer)<>before_balance+200
 OR (SELECT user_id FROM event_tickets WHERE id=t) IS DISTINCT FROM recipient
 OR (SELECT user_id FROM hg_internal.event_ticket_refunds WHERE ticket_id=t) IS DISTINCT FROM buyer
 THEN RAISE EXCEPTION 'recipient account received purchaser refund or lost ticket ownership';END IF;
 -- Guest purchaser credit waits for THEIR verified account, not an attendee's.
 roster:=replace(roster::text,'audit-group-card-','audit-group-guest-')::jsonb;
 g:=hg_create_event_group(e,NULL,jsonb_build_object('name','Guest buyer','email','guest-purchaser-'||e||'@example.invalid','phone','08012345678'),roster,'card',0,NULL,'guest-group-'||e,repeat('e',64));
 grp:=(g->>'id')::uuid;g:=hg_pay_event_group(grp,g->>'payment_reference',300,'{}');
 SELECT id INTO t FROM event_tickets WHERE group_id=grp AND tier_id=tier1;
 r:=hg_request_event_ticket_refund(admin,e,t,gen_random_uuid(),'Support approved guest purchaser wallet credit');
 IF r->>'state'<>'awaiting_account' THEN RAISE EXCEPTION 'guest purchaser refund did not wait for account';END IF;
 INSERT INTO auth.users(id,email,raw_user_meta_data,email_confirmed_at) VALUES(guest_buyer,'guest-purchaser-'||e||'@example.invalid','{}',now());
 UPDATE profiles SET campus_id=c,is_active=true WHERE id=guest_buyer;
 claim_attendee:=hg_claim_guest_event_refunds(attendee);claim_buyer:=hg_claim_guest_event_refunds(guest_buyer);claim_replay:=hg_claim_guest_event_refunds(guest_buyer);
 IF claim_attendee<>0 OR claim_buyer<>1 OR claim_replay<>0
 OR (SELECT user_id FROM event_tickets WHERE id=t) IS NOT NULL
 OR (SELECT user_id FROM hg_internal.event_ticket_refunds WHERE ticket_id=t) IS DISTINCT FROM guest_buyer
 THEN RAISE EXCEPTION 'guest purchaser refund claim counts: %, %, %; ticket owner %, buyer %, refund owner %',claim_attendee,claim_buyer,claim_replay,(SELECT user_id FROM event_tickets WHERE id=t),guest_buyer,(SELECT user_id FROM hg_internal.event_ticket_refunds WHERE ticket_id=t);END IF;
 -- A guest attendee can check in before signup, then claim their own earned HP.
 SELECT id INTO t FROM event_tickets WHERE group_id=grp AND tier_id=tier2;
 r:=hg_admit_event_ticket(e,t,admin,NULL,c,50);
 IF (r->>'claimable_hp')::integer<>50 THEN RAISE EXCEPTION 'group guest attendance promise missing';END IF;
 INSERT INTO auth.users(id,email,raw_user_meta_data,email_confirmed_at) VALUES(post_attendee,roster->1->>'email','{}',now());
 UPDATE profiles SET campus_id=c,is_active=true WHERE id=post_attendee;
 r:=hg_claim_guest_attendance_hp(post_attendee);again:=hg_claim_guest_attendance_hp(post_attendee);
 IF (r->>'claimed')::integer<>1 OR (again->>'claimed')::integer<>0
 OR (SELECT count(*) FROM hp_transactions WHERE user_id=post_attendee AND reference_type='event' AND reference_id=e AND amount=50)<>1
 THEN RAISE EXCEPTION 'group guest earned HP claim failed/replayed: %, %',r,again;END IF;
 -- Timely split confirmation includes a fully wallet-funded attendee, with no zero-value card receipt.
 roster:=replace(roster::text,'audit-group-guest-','audit-group-timely-')::jsonb;
 SELECT balance INTO before_balance FROM wallets WHERE user_id=buyer;
 g:=hg_create_event_group(e,buyer,contact,roster,'split',150,NULL,'timely-split-group-'||e,repeat('b',64));grp:=(g->>'id')::uuid;
 g:=hg_pay_event_group(grp,g->>'payment_reference',150,'{}');again:=hg_pay_event_group(grp,g->>'payment_reference',150,'{}');
 IF (SELECT count(*) FROM event_tickets WHERE group_id=grp AND status='confirmed' AND payment_status='paid')<>2
 OR (SELECT balance FROM wallets WHERE user_id=buyer)<>before_balance-150
 OR (SELECT count(*) FROM payments p JOIN event_tickets et ON et.id=p.ticket_id WHERE et.group_id=grp)<>1
 OR (SELECT sum(p.amount) FROM payments p JOIN event_tickets et ON et.id=p.ticket_id WHERE et.group_id=grp)<>150 THEN RAISE EXCEPTION 'timely split introduced zero-value card payment or repeated wallet debit';END IF;
 roster:=replace(roster::text,'audit-group-timely-','audit-group-guest-')::jsonb;
 -- Full wallet+card conservation on expiration and late payment recovery.
 roster:=replace(roster::text,'audit-group-guest-','audit-group-split-')::jsonb;
 SELECT balance INTO before_balance FROM wallets WHERE user_id=buyer;
 g:=hg_create_event_group(e,buyer,contact,roster,'split',150,NULL,'split-group-'||e,repeat('d',64));grp:=(g->>'id')::uuid;reference:=g->>'payment_reference';
 IF (SELECT balance FROM wallets WHERE user_id=buyer)<>before_balance-150 THEN RAISE EXCEPTION 'split group debit failed';END IF;
 UPDATE event_tickets SET payment_expires_at=now()-interval '1 second' WHERE group_id=grp;
 FOR t IN SELECT id FROM event_tickets WHERE group_id=grp LOOP PERFORM hg_release_expired_event_reservation(t);PERFORM hg_release_expired_event_reservation(t);END LOOP;
 IF (SELECT balance FROM wallets WHERE user_id=buyer)<>before_balance THEN RAISE EXCEPTION 'split group wallet not restored once';END IF;
 g:=hg_pay_event_group(grp,reference,150,jsonb_build_object('_recovery_reason','Late group payment after the reservation expired'));
 again:=hg_pay_event_group(grp,reference,150,jsonb_build_object('_recovery_reason','Late group payment after the reservation expired'));
 IF (SELECT balance FROM wallets WHERE user_id=buyer)<>before_balance+150
 OR EXISTS(SELECT 1 FROM event_tickets WHERE group_id=grp AND status='confirmed') THEN RAISE EXCEPTION 'late group payment double-credit or entry issued';END IF;
 IF (SELECT count(*) FROM notification_deliveries WHERE id=grp AND dispatch_payload->>'kind'='event_group_email' AND dispatch_payload->'notification'->>'email'=contact->>'email')<>1 THEN RAISE EXCEPTION 'purchaser receipt missing or duplicated';END IF;
 IF has_function_privilege('anon','public.hg_create_event_group(uuid,uuid,jsonb,jsonb,text,numeric,uuid,text,text)','execute')
 OR has_function_privilege('authenticated','public.hg_pay_event_group(uuid,text,numeric,jsonb)','execute')
 OR has_table_privilege('authenticated','hg_internal.event_ticket_groups','select') THEN RAISE EXCEPTION 'group financial/access data exposed directly';END IF;
END $test$;
SELECT 'group wallet/card/split, individual recipients/answers/QR, atomic replay/rollback, payment amount/fanout, buyer refunds, expiry and late-payment conservation passed' AS verified;
ROLLBACK;
