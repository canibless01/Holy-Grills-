-- Called only after server-side provider verification. No new ledger/table.
CREATE OR REPLACE FUNCTION public.hg_reconcile_late_order_payment(
 p_order_id uuid,p_provider text,p_reference text,p_amount numeric,p_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE
 o public.orders%ROWTYPE; payment public.payments%ROWTYPE; credit jsonb;
 resolution text; credited numeric; payment_id uuid;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 SELECT * INTO o FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','order_not_found'); END IF;
 IF o.status::text NOT IN ('cancelled','refunded') THEN RETURN jsonb_build_object('error','order_not_closed'); END IF;
 IF p_provider IS NULL OR p_provider NOT IN ('paystack','flutterwave')
 OR p_reference IS NULL OR btrim(p_reference)='' OR p_amount IS NULL OR p_amount<=0
 OR p_amount::text IN ('NaN','Infinity','-Infinity') OR p_amount<>round(p_amount,2)
 OR p_amount IS DISTINCT FROM o.card_amount_used
 OR coalesce(o.wallet_amount_used,0)+coalesce(o.card_amount_used,0)<>o.total_amount
 THEN RETURN jsonb_build_object('error','payment_mismatch'); END IF;
 SELECT * INTO payment FROM public.payments WHERE reference=p_reference FOR UPDATE;
 IF FOUND AND (payment.order_id IS DISTINCT FROM o.id OR payment.user_id IS DISTINCT FROM o.user_id
   OR payment.provider IS DISTINCT FROM p_provider OR payment.amount IS DISTINCT FROM p_amount
   OR payment.ticket_id IS NOT NULL) THEN RETURN jsonb_build_object('error','payment_reference_conflict'); END IF;
 IF payment.id IS NOT NULL AND payment.status='paid' THEN
   RETURN jsonb_build_object('success',true,'idempotent',true,
     'resolution',coalesce(payment.metadata->>'late_payment_resolution','already_settled'),
     'manual_review',payment.metadata->>'late_payment_resolution'='manual_refund_required');
 END IF;
 -- A paid row is the receipt that distinguishes a new late charge from a
 -- replay of the original charge on an order subsequently refunded.
 IF o.user_id IS NOT NULL THEN
   SELECT coalesce(sum(amount),0) INTO credited FROM public.wallet_transactions
    WHERE user_id=o.user_id AND type='credit' AND reference_type='refund' AND reference_id=o.id;
   IF credited>o.total_amount THEN RETURN jsonb_build_object('error','refund_conservation'); END IF;
   IF credited=o.total_amount THEN
     resolution:='already_settled';
   ELSE
   credit:=public.credit_wallet_atomic(o.user_id,p_amount,'Late payment on cancelled order',
     'refund',o.id,'late-order-payment',p_provider||':'||p_reference,
     jsonb_build_object('late_payment',true,'provider',p_provider,'order_id',o.id),o.campus_id);
   IF NOT coalesce((credit->>'success')::boolean,false) OR credit ? 'error'
   THEN RAISE EXCEPTION 'late_payment_credit_failed'; END IF;
   resolution:='wallet_credited';
   END IF;
 ELSE
   resolution:='manual_refund_required';
 END IF;
 INSERT INTO public.payments(order_id,user_id,campus_id,provider,reference,amount,status,confirmed_at,metadata)
 VALUES(o.id,o.user_id,o.campus_id,p_provider,p_reference,p_amount,'paid',now(),
   coalesce(p_metadata,'{}'::jsonb)||jsonb_build_object('late_payment_resolution',resolution,
     'reconciliation_required',o.user_id IS NULL))
 ON CONFLICT(reference) DO UPDATE SET status='paid',confirmed_at=coalesce(payments.confirmed_at,excluded.confirmed_at),
   metadata=payments.metadata||excluded.metadata,failure_reason=null
 WHERE payments.order_id=excluded.order_id AND payments.user_id IS NOT DISTINCT FROM excluded.user_id
   AND payments.provider=excluded.provider AND payments.amount=excluded.amount AND payments.ticket_id IS NULL
 RETURNING id INTO payment_id;
 IF payment_id IS NULL THEN RAISE EXCEPTION 'payment_reference_conflict'; END IF;
 IF o.user_id IS NOT NULL THEN
   SELECT coalesce(sum(amount),0) INTO credited FROM public.wallet_transactions
    WHERE user_id=o.user_id AND type='credit' AND reference_type='refund' AND reference_id=o.id;
   UPDATE public.orders SET wallet_refund_total=least(credited,coalesce(o.wallet_amount_used,0)),
     card_refund_total=least(o.card_amount_used,greatest(0,credited-coalesce(o.wallet_amount_used,0))),
     payment_status=CASE WHEN credited>=o.total_amount THEN 'refunded'::public.payment_status
                         ELSE 'partially_refunded'::public.payment_status END,
     payment_reference=p_reference,refunded_at=now(),payment_confirmed_at=now() WHERE id=o.id;
 ELSE
   UPDATE public.orders SET payment_status='paid',payment_reference=p_reference,
     payment_confirmed_at=now() WHERE id=o.id;
 END IF;
 INSERT INTO public.order_status_logs(order_id,status,note,metadata,campus_id)
 VALUES(o.id,o.status,'Late payment reconciled',jsonb_build_object('late_payment_resolution',resolution,
   'payment_id',payment_id,'amount',p_amount),o.campus_id);
 RETURN jsonb_build_object('success',true,'idempotent',false,'resolution',resolution,
   'manual_review',o.user_id IS NULL,'amount',p_amount);
EXCEPTION WHEN OTHERS THEN
 RETURN jsonb_build_object('error','late_payment_reconciliation_failed','debug_code',SQLSTATE);
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_reconcile_late_order_payment(uuid,text,text,numeric,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_reconcile_late_order_payment(uuid,text,text,numeric,jsonb) TO service_role;

