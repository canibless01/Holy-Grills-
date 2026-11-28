-- Skip the subscription sweep when all campus offers are gated off and there
-- is no already-incurred financial/reconciliation or customer-notice work.
-- Preserve signature, service-only grants and all existing payment locks.
DO $gate$
DECLARE body text;needle text:=$old$ IF p_action='scan' THEN
  RETURN jsonb_build_object($old$;
 replacement text:=$new$ IF p_action='scan' THEN
  IF NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pass_offers gate_offer
      WHERE gate_offer.is_active AND hg_internal.delivery_pass_sale_enabled(gate_offer.campus_id))
   AND NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pass_receipts
      WHERE method='card' AND status IN('pending','cancelled') AND next_check_at<=now())
   AND NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pass_receipts
      WHERE status IN('paid','credited','refunded') AND notified_status IS DISTINCT FROM status)
   AND NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pass_memberships
      WHERE renewal_issue IS NOT NULL AND NOT issue_notified)
   AND NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pass_memberships
      WHERE auto_renew AND paid_until<now()-interval '48 hours') THEN
   RETURN '{"skipped":true,"reason":"delivery_pass_disabled"}'::jsonb;
  END IF;
  RETURN jsonb_build_object($new$;
BEGIN
 SELECT pg_get_functiondef('public.hg_delivery_pass(uuid,text,uuid,jsonb)'::regprocedure) INTO body;
 IF strpos(body,needle)=0 THEN RAISE EXCEPTION 'Delivery pass scan changed';END IF;
 EXECUTE replace(body,needle,replacement);
END$gate$;

CREATE INDEX delivery_pass_open_issues ON hg_internal.delivery_pass_memberships(updated_at,id)
 WHERE renewal_issue IS NOT NULL AND NOT issue_notified;
