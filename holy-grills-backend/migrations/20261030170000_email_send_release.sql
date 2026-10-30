-- Give back an email send slot that was claimed but not used.
--
-- The router now *reserves* a slot before it sends (hg_record_email_send), so a
-- burst of registrations cannot all read "98 sent" at the same moment and all pick
-- the provider that only has two sends left. Reserving first means the counter is
-- the arbiter, not the last read.
--
-- The cost of reserving first is that a slot is spent before we know whether the
-- send happened, so a definite non-send (provider not configured, a quota refusal,
-- "no recipients") has to hand the slot back — otherwise a broken provider would
-- look "used up" and traffic would move away from a provider that was fine.
--
-- Ambiguous outcomes (timeout, 5xx) deliberately keep their slot: that message may
-- have been accepted, so it must count.

CREATE OR REPLACE FUNCTION public.hg_release_email_send(p_provider text, p_day date DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $function$
DECLARE v_count integer;
BEGIN
  IF coalesce(auth.role(), '') <> 'service_role' THEN
    RAISE EXCEPTION 'email_usage_forbidden' USING ERRCODE = '42501';
  END IF;
  IF p_provider NOT IN ('resend', 'onesignal') THEN
    RAISE EXCEPTION 'email_usage_invalid_provider' USING ERRCODE = '22023';
  END IF;
  UPDATE public.email_send_counters
     SET sent_count = greatest(sent_count - 1, 0),
         updated_at = now()
   WHERE provider = p_provider
     AND usage_date = coalesce(p_day, (now() AT TIME ZONE 'Africa/Lagos')::date)
  RETURNING sent_count INTO v_count;
  IF v_count IS NULL THEN
    v_count := 0;   -- nothing was claimed (or the day rolled over): nothing to give back
  END IF;
  RETURN v_count;
END;
$function$;

REVOKE ALL ON FUNCTION public.hg_release_email_send(text, date) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_release_email_send(text, date) TO service_role;
