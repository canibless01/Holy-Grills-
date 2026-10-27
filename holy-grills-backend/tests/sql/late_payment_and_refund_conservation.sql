-- Synthetic payment states; no gateway call. Every fixture/ledger change rolls back.
BEGIN;
SET LOCAL request.jwt.claims = '{"role":"service_role"}';
DO $audit$
DECLARE
 u uuid; a uuid; c uuid:=gen_random_uuid(); o uuid; guest_order uuid;
 result jsonb; amount numeric; before_balance numeric; ref text; i integer;
BEGIN
 SELECT p.id INTO u FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id
 WHERE p.role::text='student' AND p.is_active AND p.full_name ILIKE '%audit%' AND c.name ILIKE '%audit%' LIMIT 1;
 SELECT id INTO a FROM public.profiles WHERE role::text='super_admin' AND is_active LIMIT 1;
 IF u IS NULL OR a IS NULL THEN RAISE EXCEPTION 'existing audit actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Late payments','audit-late-payment-'||c);
 UPDATE public.profiles SET campus_id=c WHERE id=u;
 SELECT balance INTO before_balance FROM public.wallets WHERE user_id=u;
 IF NOT FOUND THEN RAISE EXCEPTION 'audit wallet required'; END IF;
 INSERT INTO public.orders(user_id,campus_id,subtotal,total_amount,wallet_amount_used,card_amount_used,delivery_type)
 VALUES(u,c,2300,2300,500,1800,'off_campus') RETURNING id INTO o;
 ref:='AUDIT-LATE-'||o;
 INSERT INTO public.payments(order_id,user_id,campus_id,provider,reference,amount) VALUES(o,u,c,'paystack',ref,1800);
 result:=public.hg_refund_order_atomic(o,u,'customer-cancel',null,'[AUDIT rollback] cancel pending split',true);
 IF NOT coalesce((result->>'success')::boolean,false) OR (result->>'refund_amount')::numeric<>500
 THEN RAISE EXCEPTION 'pending split cancellation failed'; END IF;
 result:=public.hg_reconcile_late_order_payment(o,'paystack',ref,1800,'{"audit":true}');
 IF result->>'resolution'<>'wallet_credited' OR (result->>'amount')::numeric<>1800
 THEN RAISE EXCEPTION 'late split remainder recovery failed: %',result; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>before_balance+2300
 OR (SELECT status::text FROM public.orders WHERE id=o)<>'cancelled'
 OR (SELECT payment_status::text FROM public.orders WHERE id=o)<>'refunded'
 OR (SELECT wallet_refund_total+card_refund_total FROM public.orders WHERE id=o)<>2300
 THEN RAISE EXCEPTION 'late split ledger/status/counter conservation failed'; END IF;
 result:=public.hg_reconcile_late_order_payment(o,'paystack',ref,1800,'{}');
 IF NOT coalesce((result->>'idempotent')::boolean,false)
 OR (SELECT balance FROM public.wallets WHERE user_id=u)<>before_balance+2300
 THEN RAISE EXCEPTION 'late replay repeated credit'; END IF;
 result:=public.hg_reconcile_late_order_payment(o,'paystack',ref,1700,'{}');
 IF result->>'error'<>'payment_mismatch' THEN RAISE EXCEPTION 'wrong amount accepted'; END IF;
 -- Partial then full refunds, with and without a historical paid-payment row.
 FOR i IN 1..2 LOOP
   INSERT INTO public.orders(user_id,campus_id,subtotal,total_amount,wallet_amount_used,card_amount_used,
      payment_status,delivery_type)
   VALUES(u,c,1000,1000,400,600,'paid','off_campus') RETURNING id INTO o;
   ref:='AUDIT-REFUNDED-'||o;
   IF i=1 THEN
     INSERT INTO public.payments(order_id,user_id,campus_id,provider,reference,amount,status)
     VALUES(o,u,c,'paystack',ref,600,'paid');
   END IF;
   result:=public.hg_refund_order_atomic(o,a,'partial',100,'[AUDIT rollback] partial',false);
   IF NOT coalesce((result->>'success')::boolean,false) THEN RAISE EXCEPTION 'partial refund failed'; END IF;
   result:=public.hg_refund_order_atomic(o,a,'partial',100,'[AUDIT rollback] replay',false);
   IF NOT coalesce((result->>'idempotent')::boolean,false) THEN RAISE EXCEPTION 'partial replay not stable'; END IF;
   result:=public.hg_refund_order_atomic(o,a,'remaining',null,'[AUDIT rollback] remainder',false);
   IF NOT coalesce((result->>'success')::boolean,false) OR (result->>'refund_amount')::numeric<>900
   THEN RAISE EXCEPTION 'remaining refund failed'; END IF;
   SELECT balance INTO amount FROM public.wallets WHERE user_id=u;
   result:=public.hg_reconcile_late_order_payment(o,'paystack',ref,600,'{}');
   IF result->>'resolution'<>'already_settled'
   OR (SELECT balance FROM public.wallets WHERE user_id=u)<>amount
   THEN RAISE EXCEPTION 'settled/refunded original charge credited twice'; END IF;
 END LOOP;
 -- Historical partial card refund without a paid receipt: recover only the remainder.
 INSERT INTO public.orders(user_id,campus_id,subtotal,total_amount,wallet_amount_used,card_amount_used,
    status,payment_status,delivery_type,wallet_refund_total,card_refund_total)
 VALUES(u,c,2300,2300,500,1800,'cancelled','partially_refunded','off_campus',500,500) RETURNING id INTO o;
 result:=public.credit_wallet_atomic(u,1000,'[AUDIT rollback] prior partial refund','refund',o,
   'audit-prior-refund',o::text,'{}',c);
 IF NOT (result->>'success')::boolean THEN RAISE EXCEPTION 'prior refund setup failed'; END IF;
 result:=public.hg_reconcile_late_order_payment(o,'paystack','AUDIT-PARTIAL-'||o,1800,'{}');
 IF (result->>'amount')::numeric<>1300
 OR (SELECT wallet_refund_total+card_refund_total FROM public.orders WHERE id=o)<>2300
 THEN RAISE EXCEPTION 'late credit exceeded unreturned collected funds'; END IF;
 INSERT INTO public.orders(guest_email,campus_id,subtotal,total_amount,card_amount_used,status,payment_status,delivery_type)
 VALUES('audit-late@example.invalid',c,1800,1800,1800,'cancelled','failed','off_campus') RETURNING id INTO guest_order;
 ref:='AUDIT-GUEST-'||guest_order;
 result:=public.hg_reconcile_late_order_payment(guest_order,'paystack',ref,1800,'{}');
 IF result->>'resolution'<>'manual_refund_required' OR NOT (result->>'manual_review')::boolean
 OR NOT EXISTS(SELECT 1 FROM public.payments WHERE reference=ref AND status='paid'
     AND metadata->>'late_payment_resolution'='manual_refund_required')
 OR (SELECT status::text FROM public.orders WHERE id=guest_order)<>'cancelled'
 THEN RAISE EXCEPTION 'guest charge not durably marked for manual review'; END IF;
 result:=public.hg_reconcile_late_order_payment(guest_order,'paystack',ref,1800,'{}');
 IF NOT (result->>'idempotent')::boolean OR NOT (result->>'manual_review')::boolean
 THEN RAISE EXCEPTION 'guest replay lost manual-review state'; END IF;
 IF (SELECT balance FROM public.wallets WHERE user_id=u)<>before_balance+6600
 THEN RAISE EXCEPTION 'final wallet conservation failed'; END IF;
END;
$audit$;
SELECT 'passed' AS late_payment_and_refund_conservation;
ROLLBACK;
