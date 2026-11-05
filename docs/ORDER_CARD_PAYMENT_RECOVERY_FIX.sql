-- Reuse the existing payment ledger and unique provider reference.
-- Confirmation must serialize against cancellation and charge only the card remainder.
CREATE OR REPLACE FUNCTION public.hg_mark_order_paid(
  p_order_id uuid, p_provider text DEFAULT NULL, p_provider_reference text DEFAULT NULL,
  p_amount numeric DEFAULT NULL, p_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_payment public.payments%ROWTYPE;
  v_payment_id uuid;
BEGIN
  SELECT * INTO v_order FROM public.orders WHERE id=p_order_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'order_payment_not_found'; END IF;
  IF p_provider NOT IN ('paystack','flutterwave') OR p_provider IS NULL
     OR p_provider_reference IS NULL OR btrim(p_provider_reference)=''
     OR p_amount IS NULL OR p_amount<=0 OR p_amount::text IN ('NaN','Infinity','-Infinity')
     OR p_amount<>round(p_amount,2) OR p_amount IS DISTINCT FROM v_order.card_amount_used
     OR coalesce(v_order.wallet_amount_used,0)+coalesce(v_order.card_amount_used,0)<>v_order.total_amount THEN
    RAISE EXCEPTION 'order_payment_mismatch';
  END IF;
  SELECT * INTO v_payment FROM public.payments WHERE reference=p_provider_reference FOR UPDATE;
  IF FOUND AND (v_payment.order_id IS DISTINCT FROM p_order_id OR v_payment.provider IS DISTINCT FROM p_provider
                OR v_payment.amount IS DISTINCT FROM p_amount OR v_payment.ticket_id IS NOT NULL) THEN
    RAISE EXCEPTION 'order_payment_reference_conflict';
  END IF;
  IF v_order.payment_status::text IN ('paid','partially_refunded') THEN
    IF v_payment.id IS NOT NULL AND v_payment.status='paid' THEN RETURN NULL; END IF;
    RAISE EXCEPTION 'order_payment_already_paid';
  END IF;
  IF v_order.status::text NOT IN ('received','paid') OR v_order.payment_status::text IN ('refunded','cancelled') THEN
    RAISE EXCEPTION 'order_payment_closed';
  END IF;
  INSERT INTO public.payments(order_id,user_id,campus_id,provider,reference,amount,status,confirmed_at,metadata)
    VALUES(p_order_id,v_order.user_id,v_order.campus_id,p_provider,p_provider_reference,p_amount,'paid',now(),coalesce(p_metadata,'{}'))
    ON CONFLICT(reference) DO UPDATE SET status='paid',confirmed_at=coalesce(payments.confirmed_at,excluded.confirmed_at),
      metadata=payments.metadata||excluded.metadata
    WHERE payments.order_id=excluded.order_id AND payments.provider=excluded.provider
      AND payments.amount=excluded.amount AND payments.ticket_id IS NULL
    RETURNING id INTO v_payment_id;
  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'order_payment_reference_conflict'; END IF;
  -- Payment completion does not start kitchen preparation.
  UPDATE public.orders SET payment_status='paid',payment_reference=p_provider_reference,
    paid_at=coalesce(paid_at,now()),payment_confirmed_at=coalesce(payment_confirmed_at,now()),updated_at=now()
    WHERE id=p_order_id;
  RETURN v_payment_id;
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_mark_order_paid(uuid,text,text,numeric,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_mark_order_paid(uuid,text,text,numeric,jsonb) TO service_role;
REVOKE ALL ON TABLE public.payments FROM anon;
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON TABLE public.payments FROM authenticated;
GRANT SELECT ON TABLE public.payments TO authenticated;
NOTIFY pgrst,'reload schema';
