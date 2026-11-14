-- Application-level email send counters.
--
-- The only existing fallback switches provider after the provider *says* it is out
-- of quota (429 / daily_quota_exceeded / "monthly email limit"). Resend does not
-- always report that — a free plan can simply stop accepting, a shared key can be
-- suspended, or the 100th message of the day can be rejected with a shape we do not
-- recognise. Counting our own accepted sends per provider per day lets the router
-- pre-empt known limits without waiting for a rejection.
--
-- This is a fallback, not a replacement: neither provider limit is trusted blindly
-- (see app/services/email_usage.py — a limit of 0 or a failed counter read disables
-- the pre-emption and the old quota-rejection path still decides).

CREATE TABLE IF NOT EXISTS public.email_send_counters (
  provider    text NOT NULL CHECK (provider IN ('resend', 'onesignal')),
  usage_date  date NOT NULL,
  sent_count  integer NOT NULL DEFAULT 0 CHECK (sent_count >= 0),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, usage_date)
);

-- Server-only bookkeeping: no policies, so anon/authenticated can read nothing.
ALTER TABLE public.email_send_counters ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.email_send_counters FROM anon, authenticated;

-- Atomic increment. Called once per accepted provider send by the backend, so two
-- workers sending at the same moment cannot under-count and blow the daily limit.
CREATE OR REPLACE FUNCTION public.hg_record_email_send(p_provider text, p_day date DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $function$
DECLARE v_count integer;
BEGIN
  IF coalesce(auth.role(), '') <> 'service_role' THEN
    RAISE EXCEPTION 'email_usage_forbidden' USING ERRCODE = '42501';
  END IF;
  IF p_provider NOT IN ('resend', 'onesignal') THEN
    RAISE EXCEPTION 'email_usage_invalid_provider' USING ERRCODE = '22023';
  END IF;
  INSERT INTO public.email_send_counters(provider, usage_date, sent_count)
  VALUES (p_provider, coalesce(p_day, (now() AT TIME ZONE 'Africa/Lagos')::date), 1)
  ON CONFLICT (provider, usage_date)
  DO UPDATE SET sent_count = public.email_send_counters.sent_count + 1, updated_at = now()
  RETURNING sent_count INTO v_count;
  RETURN v_count;
END;
$function$;

REVOKE ALL ON FUNCTION public.hg_record_email_send(text, date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_record_email_send(text, date) TO service_role;

-- Today's counts for every provider that has sent anything, plus the limits the
-- admin panel displays. Read by the email health endpoint.
CREATE OR REPLACE FUNCTION public.hg_email_send_counts(p_day date DEFAULT NULL)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path = public STABLE AS $function$
  SELECT coalesce(jsonb_object_agg(provider, sent_count), '{}'::jsonb)
  FROM public.email_send_counters
  WHERE usage_date = coalesce(p_day, (now() AT TIME ZONE 'Africa/Lagos')::date);
$function$;

REVOKE ALL ON FUNCTION public.hg_email_send_counts(date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_email_send_counts(date) TO service_role;
