CREATE OR REPLACE FUNCTION public.credit_wallet_atomic(p_user_id uuid, p_amount numeric, p_reason text, p_reference_type text, p_reference_id uuid, p_provider text, p_provider_reference text, p_metadata jsonb, p_campus_id uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_balance NUMERIC;
  v_txn_id UUID;
  v_wallet_campus_id uuid;
  v_profile_campus_id uuid;
  v_effective_campus_id uuid;
BEGIN
  IF p_user_id IS NULL OR p_amount IS NULL OR p_amount <= 0 OR p_amount::text IN ('NaN','Infinity','-Infinity') THEN
    RETURN jsonb_build_object('success',false,'error','invalid_credit_amount');
  END IF;
  -- Serialize event identity first, then credits for the wallet. Replay checks
  -- must happen after these locks, rather than before the wallet row lock.
  IF p_provider IS NOT NULL AND p_provider_reference IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-event:' || p_provider || ':' || p_provider_reference, 0));
    IF EXISTS (SELECT 1 FROM public.wallet_transactions WHERE provider=p_provider AND provider_reference=p_provider_reference AND type='credit' AND user_id IS DISTINCT FROM p_user_id) THEN
      RETURN jsonb_build_object('success',false,'error','credit_event_owner_mismatch');
    END IF;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-wallet-credit:' || p_user_id::text, 0));

  -- Legacy callers without provider/event identity use the reference fallback.
  IF (p_provider IS NULL OR p_provider_reference IS NULL) AND p_reference_type IS NOT NULL AND p_reference_id IS NOT NULL THEN
    SELECT id, balance_after INTO v_txn_id, v_balance
    FROM public.wallet_transactions
    WHERE user_id = p_user_id AND reference_type = p_reference_type AND reference_id = p_reference_id AND type = 'credit' AND amount = p_amount;
    IF FOUND THEN
      RETURN jsonb_build_object('success', true, 'new_balance', v_balance, 'transaction_id', v_txn_id, 'replayed', true);
    END IF;
  END IF;

  IF p_provider_reference IS NOT NULL AND p_provider IS NOT NULL THEN
    SELECT id, balance_after INTO v_txn_id, v_balance
    FROM public.wallet_transactions
    WHERE user_id = p_user_id AND provider = p_provider AND provider_reference = p_provider_reference AND type = 'credit';
    IF FOUND THEN
      RETURN jsonb_build_object('success', true, 'new_balance', v_balance, 'transaction_id', v_txn_id, 'replayed', true);
    END IF;
  END IF;

  SELECT campus_id INTO v_profile_campus_id FROM public.profiles WHERE id = p_user_id;

  SELECT balance, campus_id INTO v_balance, v_wallet_campus_id FROM public.wallets WHERE user_id = p_user_id FOR UPDATE;
  IF NOT FOUND THEN
    INSERT INTO public.wallets (user_id, balance, currency, campus_id)
    VALUES (p_user_id, p_amount, 'NGN', coalesce(p_campus_id, v_profile_campus_id))
    RETURNING balance, campus_id INTO v_balance, v_wallet_campus_id;
  ELSE
    v_balance := v_balance + p_amount;
    UPDATE public.wallets SET balance = v_balance, updated_at = now() WHERE user_id = p_user_id;
  END IF;

  v_effective_campus_id := coalesce(v_profile_campus_id, v_wallet_campus_id, p_campus_id);

  INSERT INTO public.wallet_transactions (
    user_id, type, amount, balance_after, reason, reference_type, reference_id, provider, provider_reference, metadata, campus_id
  )
  VALUES (
    p_user_id, 'credit', p_amount, v_balance, p_reason, p_reference_type, p_reference_id, p_provider, p_provider_reference, p_metadata, v_effective_campus_id
  )
  RETURNING id INTO v_txn_id;

  RETURN jsonb_build_object('success', true, 'new_balance', v_balance, 'transaction_id', v_txn_id);
END;
$function$
