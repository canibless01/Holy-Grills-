-- Durable notices for paused automatic funding, sharing the existing worker
-- and notification dispatch recovery. No provider call or balance mutation.
ALTER TABLE hg_internal.wallet_funding_plans ADD COLUMN attention_notified boolean NOT NULL DEFAULT false,
 ADD COLUMN attention_next_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX wallet_funding_attention_due ON hg_internal.wallet_funding_plans(attention_next_at)
 WHERE state='attention' AND NOT attention_notified;
CREATE FUNCTION public.hg_wallet_funding_attention(p_action text,p_id uuid DEFAULT NULL,p_limit integer DEFAULT 5)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb;
BEGIN
 IF p_action='claim' THEN
  WITH due AS (
   SELECT id FROM hg_internal.wallet_funding_plans WHERE state='attention' AND NOT attention_notified AND attention_next_at<=now()
   ORDER BY attention_next_at LIMIT least(greatest(coalesce(p_limit,5),0),20) FOR UPDATE SKIP LOCKED
  ), claimed AS (
   UPDATE hg_internal.wallet_funding_plans f SET attention_next_at=now()+interval '15 minutes' FROM due WHERE f.id=due.id
   RETURNING f.id,f.user_id,f.campus_id,f.last_issue
  ) SELECT coalesce(jsonb_agg(to_jsonb(claimed)),'[]') INTO result FROM claimed;
  RETURN result;
 ELSIF p_action='done' THEN
  UPDATE hg_internal.wallet_funding_plans SET attention_notified=true WHERE id=p_id AND state='attention';
  RETURN '{}';
 END IF;
 RAISE EXCEPTION 'Unknown funding notice operation';
END $$;
REVOKE ALL ON FUNCTION public.hg_wallet_funding_attention(text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_wallet_funding_attention(text,uuid,integer) TO service_role;
