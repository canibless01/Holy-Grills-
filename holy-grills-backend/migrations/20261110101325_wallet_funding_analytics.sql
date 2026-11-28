CREATE INDEX wallet_analytics_history_window ON public.wallet_transactions(created_at,campus_id);
CREATE INDEX wallet_funding_succeeded_transaction ON hg_internal.wallet_funding_attempts(transaction_id) WHERE state='succeeded' AND transaction_id IS NOT NULL;
-- One read-only snapshot. Card credentials and customer identifiers stay private.
CREATE FUNCTION public.hg_wallet_funding_analytics(p_actor uuid,p_campus uuid DEFAULT NULL,p_from date DEFAULT NULL,p_to date DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%rowtype;scope uuid;result jsonb;
 as_of timestamptz:=now();today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
 first_day date;last_day date;range_start timestamptz;range_end timestamptz;forecast_end timestamptz;
BEGIN
 SELECT * INTO actor FROM public.profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN('admin','super_admin') THEN RAISE EXCEPTION 'wallet_analytics_forbidden' USING ERRCODE='42501'; END IF;
 IF actor.role::text='admin' THEN
  IF actor.campus_id IS NULL OR (p_campus IS NOT NULL AND p_campus IS DISTINCT FROM actor.campus_id) THEN RAISE EXCEPTION 'wallet_analytics_forbidden' USING ERRCODE='42501'; END IF;
  scope:=actor.campus_id;
 ELSE scope:=p_campus; END IF;
 IF scope IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=scope) THEN RAISE EXCEPTION 'wallet_analytics_campus_invalid'; END IF;
 first_day:=coalesce(p_from,today-29);last_day:=coalesce(p_to,today);
 IF last_day<first_day OR last_day-first_day>365 THEN RAISE EXCEPTION 'wallet_analytics_date_invalid'; END IF;
 range_start:=first_day::timestamp AT TIME ZONE 'Africa/Lagos';range_end:=(last_day+1)::timestamp AT TIME ZONE 'Africa/Lagos';
 forecast_end:=(today+90)::timestamp AT TIME ZONE 'Africa/Lagos';
 WITH customers AS MATERIALIZED (
  -- Exclude current super-admin accounts from every metric, not just balances.
  SELECT id,campus_id,is_active FROM public.profiles WHERE role::text<>'super_admin'
 ), balances AS (
  SELECT w.balance,w.currency,c.is_active,
   w.currency='NGN' AND w.balance>=0 AND w.balance::text NOT IN('NaN','Infinity','-Infinity') AS valid
  FROM public.wallets w JOIN customers c ON c.id=w.user_id WHERE scope IS NULL OR c.campus_id=scope
 ), plans AS MATERIALIZED (
  SELECT f.id,f.user_id,f.amount_kobo,f.interval_days,f.stop_after,f.end_at,f.state,f.successful_payments,
   f.total_credited_kobo,f.next_due_at,
   c.is_active AND c.campus_id IS NOT DISTINCT FROM f.campus_id AS owner_eligible,
   nullif(btrim(f.card_authorization->>'authorization_code'),'') IS NOT NULL AS card_present,
   EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts a WHERE a.plan_id=f.id AND a.state IN('setup','handed_off')) AS awaiting_payment
  FROM hg_internal.wallet_funding_plans f JOIN customers c ON c.id=f.user_id WHERE scope IS NULL OR f.campus_id=scope
 ), eligible AS MATERIALIZED (
  SELECT * FROM plans WHERE state='active' AND owner_eligible AND card_present AND NOT awaiting_payment
   AND next_due_at IS NOT NULL AND interval_days BETWEEN 1 AND 365
   AND (end_at IS NULL OR end_at>as_of) AND (stop_after IS NULL OR successful_payments<stop_after)
 ), forecast_events AS MATERIALIZED (
  -- At most one overdue contribution now; never count a missed-window burst.
  SELECT e.amount_kobo,due.at FROM eligible e
  CROSS JOIN LATERAL generate_series(0,least(89,coalesce(e.stop_after-e.successful_payments-1,89))) cycle(n)
  CROSS JOIN LATERAL (SELECT greatest(e.next_due_at,as_of)+make_interval(days=>cycle.n*e.interval_days) AS at) due
  WHERE due.at<forecast_end AND (e.end_at IS NULL OR due.at<e.end_at)
 ), transactions AS MATERIALIZED (
  SELECT t.id,t.type,t.amount,t.reference_type,t.created_at,
   t.type='credit' AND t.provider='paystack' AND t.reference_type IN('topup','bank_transfer') AS is_funding,
   EXISTS(SELECT 1 FROM hg_internal.wallet_funding_attempts a WHERE a.transaction_id=t.id AND a.state='succeeded') AS is_auto,
   (t.type='refund' OR (t.type='credit' AND t.reference_type IN('refund','event_ticket_refund'))) AS is_refund
  FROM public.wallet_transactions t JOIN customers c ON c.id=t.user_id
  WHERE t.created_at>=range_start AND t.created_at<range_end AND (scope IS NULL OR t.campus_id=scope)
   AND t.amount>0 AND t.amount::text NOT IN('NaN','Infinity','-Infinity')
 ), transfers AS MATERIALIZED (
  SELECT t.amount_kobo,t.created_at FROM hg_internal.wallet_transfers t
  JOIN customers sender ON sender.id=t.sender_id JOIN customers recipient ON recipient.id=t.recipient_id
  WHERE t.created_at>=range_start AND t.created_at<range_end AND (scope IS NULL OR t.campus_id=scope)
 ), current_attempts AS (
  SELECT a.state,a.updated_at,f.state AS plan_state,f.amount_kobo
  FROM hg_internal.wallet_funding_attempts a JOIN plans f ON f.id=a.plan_id
 ), history_daily AS (
  SELECT (created_at AT TIME ZONE 'Africa/Lagos')::date AS day,
   coalesce(sum(amount) FILTER(WHERE is_funding AND NOT is_auto),0) AS manual_funding,
   coalesce(sum(amount) FILTER(WHERE is_funding AND is_auto),0) AS automatic_funding,
   coalesce(sum(amount) FILTER(WHERE is_refund),0) AS refunds,
   coalesce(sum(amount) FILTER(WHERE type='debit' AND reference_type IS DISTINCT FROM 'wallet_transfer'),0) AS wallet_debits
  FROM transactions GROUP BY 1
 ), forecast_daily AS (
  SELECT (at AT TIME ZONE 'Africa/Lagos')::date AS day,sum(amount_kobo)::numeric/100 AS amount,count(*) AS contributions
  FROM forecast_events GROUP BY 1
 )
 SELECT jsonb_build_object('as_of',as_of,'timezone','Africa/Lagos','currency','NGN','campus_id',scope,'excluded_roles',jsonb_build_array('super_admin'),
  'period',jsonb_build_object('from_date',first_day,'to_date',last_day),
  'balances',(SELECT jsonb_build_object(
   'outstanding',coalesce(sum(balance) FILTER(WHERE valid),0),
   'wallet_accounts',count(*) FILTER(WHERE valid),'funded_accounts',count(*) FILTER(WHERE valid AND balance>0),
   'inactive_balance',coalesce(sum(balance) FILTER(WHERE valid AND NOT is_active),0),
   'average_funded_balance',coalesce(avg(balance) FILTER(WHERE valid AND balance>0),0),
   'balance_issues',count(*) FILTER(WHERE NOT valid OR valid IS NULL)) FROM balances),
  'activity',(SELECT jsonb_build_object(
   'funding_received',coalesce(sum(amount) FILTER(WHERE is_funding),0),
   'automatic_received',coalesce(sum(amount) FILTER(WHERE is_funding AND is_auto),0),
   'automatic_contributions',count(*) FILTER(WHERE is_funding AND is_auto),
   'manual_funding_received',coalesce(sum(amount) FILTER(WHERE is_funding AND NOT is_auto),0),
   'refunds_credited',coalesce(sum(amount) FILTER(WHERE is_refund),0),
   'other_credits',coalesce(sum(amount) FILTER(WHERE type='credit' AND NOT coalesce(is_funding,false) AND NOT coalesce(is_refund,false) AND reference_type IS DISTINCT FROM 'wallet_transfer'),0),
   'wallet_debits',coalesce(sum(amount) FILTER(WHERE type='debit' AND reference_type IS DISTINCT FROM 'wallet_transfer'),0),
   'adjustments',count(*) FILTER(WHERE type='adjustment')) FROM transactions),
  'transfers',(SELECT jsonb_build_object('count',count(*),'volume',coalesce(sum(amount_kobo),0)::numeric/100) FROM transfers),
  'automatic_funding',(SELECT jsonb_build_object('owners',count(DISTINCT user_id),'plans',count(*),
   'states',jsonb_build_object('active',count(*) FILTER(WHERE state='active'),'draft',count(*) FILTER(WHERE state='draft'),
    'attention',count(*) FILTER(WHERE state='attention'),'stopped',count(*) FILTER(WHERE state='stopped'),'completed',count(*) FILTER(WHERE state='completed')),
   'lifetime_credited',coalesce(sum(total_credited_kobo),0)::numeric/100,'lifetime_contributions',coalesce(sum(successful_payments),0)) FROM plans),
  'payment_health',(SELECT jsonb_build_object('awaiting_first_payment',count(*) FILTER(WHERE state='setup' AND plan_state='draft'),
   'awaiting_confirmation',count(*) FILTER(WHERE state='handed_off'),
   'unconfirmed_amount',coalesce(sum(amount_kobo) FILTER(WHERE state='handed_off'),0)::numeric/100,
   'failed_in_period',count(*) FILTER(WHERE state='failed' AND updated_at>=range_start AND updated_at<range_end)) FROM current_attempts),
  'projection',jsonb_build_object('eligible_plans',(SELECT count(*) FROM eligible),
   'excluded_active_plans',(SELECT count(*) FROM plans WHERE state='active')-(SELECT count(*) FROM eligible),
   'overdue_plans',(SELECT count(*) FROM eligible WHERE next_due_at<as_of),
   'horizons',(SELECT jsonb_agg(jsonb_build_object('days',h.days,'through_date',today+h.days-1,
      'amount',coalesce((SELECT sum(amount_kobo)::numeric/100 FROM forecast_events WHERE at<(today+h.days)::timestamp AT TIME ZONE 'Africa/Lagos'),0),
      'contributions',(SELECT count(*) FROM forecast_events WHERE at<(today+h.days)::timestamp AT TIME ZONE 'Africa/Lagos')) ORDER BY h.days)
     FROM (VALUES(7),(30),(90)) h(days)),
   'daily',(SELECT jsonb_agg(jsonb_build_object('date',today+d.n,'amount',coalesce(f.amount,0),'contributions',coalesce(f.contributions,0)) ORDER BY d.n)
     FROM generate_series(0,29) d(n) LEFT JOIN forecast_daily f ON f.day=today+d.n)),
  'daily_history',(SELECT jsonb_agg(jsonb_build_object('date',first_day+d.n,
    'manual_funding',coalesce(h.manual_funding,0),'automatic_funding',coalesce(h.automatic_funding,0),
    'refunds',coalesce(h.refunds,0),'wallet_debits',coalesce(h.wallet_debits,0)) ORDER BY d.n)
   FROM generate_series(0,last_day-first_day) d(n) LEFT JOIN history_daily h ON h.day=first_day+d.n)
 ) INTO result;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_wallet_funding_analytics(uuid,uuid,date,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_wallet_funding_analytics(uuid,uuid,date,date) TO service_role;
