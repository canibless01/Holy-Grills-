-- Keep interrupted external sends distinct from confirmed rejection. Neither
-- state is automatically resent without provider evidence.
ALTER TABLE public.newsletter_deliveries DROP CONSTRAINT newsletter_deliveries_status_check;
ALTER TABLE public.newsletter_deliveries ADD CONSTRAINT newsletter_deliveries_status_check CHECK(status IN('sending','sent','failed','uncertain'));
CREATE OR REPLACE FUNCTION public.hg_claim_newsletter_delivery(p_campaign uuid,p_subscription uuid,p_email text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c public.newsletter_campaigns%rowtype;s public.newsletter_subscriptions%rowtype;delivery uuid;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO c FROM public.newsletter_campaigns WHERE id=p_campaign FOR UPDATE;
 IF NOT FOUND OR c.status<>'sending' THEN RETURN NULL;END IF;
 SELECT * INTO s FROM public.newsletter_subscriptions WHERE id=p_subscription FOR SHARE;
 IF NOT FOUND OR s.unsubscribed_at IS NOT NULL OR NOT coalesce(s.is_confirmed,false) OR s.created_at>c.created_at OR (c.campus_id IS NOT NULL AND s.campus_id IS DISTINCT FROM c.campus_id) OR lower(btrim(s.email::text)) IS DISTINCT FROM lower(btrim(p_email)) THEN RETURN NULL;END IF;
 INSERT INTO public.newsletter_deliveries(campaign_id,subscription_id,status) VALUES(c.id,s.id,'sending') ON CONFLICT(campaign_id,subscription_id) DO NOTHING RETURNING id INTO delivery;
 IF delivery IS NULL THEN RETURN NULL;END IF;
 RETURN jsonb_build_object('id',delivery);
END $$;
CREATE OR REPLACE FUNCTION public.hg_refresh_newsletter_summary(p_campaign uuid,p_uncertain_notice text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c public.newsletter_campaigns%rowtype;accepted integer;rejected integer;unknown_count integer;inflight integer;pending boolean;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_NEWSLETTER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO c FROM public.newsletter_campaigns WHERE id=p_campaign FOR UPDATE;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT count(*) FILTER(WHERE status='sent'),count(*) FILTER(WHERE status='failed'),count(*) FILTER(WHERE status='uncertain'),count(*) FILTER(WHERE status='sending') INTO accepted,rejected,unknown_count,inflight FROM public.newsletter_deliveries WHERE campaign_id=c.id;
 SELECT EXISTS(SELECT 1 FROM public.newsletter_subscriptions s WHERE s.is_confirmed AND s.unsubscribed_at IS NULL AND s.created_at<=c.created_at AND (c.campus_id IS NULL OR s.campus_id=c.campus_id) AND NOT EXISTS(SELECT 1 FROM public.newsletter_deliveries d WHERE d.campaign_id=c.id AND d.subscription_id=s.id)) INTO pending;
 UPDATE public.newsletter_campaigns SET sent_count=accepted,failed_count=rejected,
  total_recipients=CASE WHEN NOT pending AND inflight=0 THEN accepted+rejected+unknown_count ELSE total_recipients END,
  status=CASE WHEN status IN('queued','sending') AND NOT pending AND inflight=0 THEN CASE WHEN rejected+unknown_count>0 THEN 'partial' ELSE 'sent' END ELSE status END,
  completed_at=CASE WHEN status IN('queued','sending') AND NOT pending AND inflight=0 THEN coalesce(completed_at,now()) ELSE completed_at END,
  last_error=CASE WHEN unknown_count>0 THEN p_uncertain_notice ELSE last_error END WHERE id=c.id RETURNING * INTO c;
 RETURN jsonb_build_object('status',c.status,'sent',accepted,'failed',rejected,'uncertain',unknown_count,'inflight',inflight,'pending',pending,'done',c.status NOT IN('queued','sending'));
END $$;
REVOKE ALL ON FUNCTION public.hg_claim_newsletter_delivery(uuid,uuid,text),public.hg_refresh_newsletter_summary(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_newsletter_delivery(uuid,uuid,text),public.hg_refresh_newsletter_summary(uuid,text) TO service_role;
