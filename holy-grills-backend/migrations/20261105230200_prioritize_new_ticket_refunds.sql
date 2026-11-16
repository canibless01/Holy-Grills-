-- Bank processing may take days. Its polling must not starve a newly queued
-- refund or a completed wallet refund's customer notice.
CREATE OR REPLACE FUNCTION public.hg_due_event_refunds(p_limit integer DEFAULT 10)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(id),'[]') FROM (SELECT id FROM hg_internal.event_ticket_refunds WHERE
 (state='completed' AND user_id IS NOT NULL AND NOT notified) OR (destination='paystack' AND next_at<=now() AND
 (state IN ('queued','processing') OR (state IN ('claimed','sending','checking') AND lease_until<=now())))
 ORDER BY CASE WHEN state IN ('queued','claimed','sending') THEN 0 WHEN state='completed' THEN 1 ELSE 2 END,
 next_at,created_at,id LIMIT greatest(1,least(coalesce(p_limit,10),50)))q;
$$;
