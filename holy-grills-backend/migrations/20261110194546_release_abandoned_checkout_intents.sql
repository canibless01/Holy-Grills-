CREATE TABLE hg_internal.checkout_intent_closures (
 intent_key text PRIMARY KEY,owner_id uuid,campus_id uuid NOT NULL,
 guest_contact_hash text,created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE hg_internal.checkout_intent_closures ENABLE ROW LEVEL SECURITY;
CREATE POLICY checkout_intent_closures_service ON hg_internal.checkout_intent_closures FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.checkout_intent_closures FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.checkout_intent_closures TO service_role;

-- Serialize intent closure with even a late/in-flight creation, independently of
-- the delivery date. Preserve the current authoritative calculator and refunds.
DO $patch$
DECLARE definition text;needle text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO STRICT definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='hg_create_order_atomic';
 needle:='    IF p_user_id IS NOT NULL AND COALESCE(auth.role(), '''')';
 IF position(needle IN definition)=0 OR position('checkout_intent_closures' IN definition)>0 THEN RAISE EXCEPTION 'Unexpected checkout admission definition'; END IF;
 definition:=replace(definition,needle,E'    IF p_idempotency_key IS NOT NULL THEN\n'
  ||E'      PERFORM pg_advisory_xact_lock(hashtextextended(''hg-checkout-intent:''||p_idempotency_key,0));\n'
  ||E'      IF EXISTS(SELECT 1 FROM hg_internal.checkout_intent_closures WHERE intent_key=p_idempotency_key) THEN RETURN jsonb_build_object(''error'',''checkout_intent_closed''); END IF;\n'
  ||E'    END IF;\n'||needle);
 EXECUTE definition;
END $patch$;
CREATE FUNCTION public.hg_abandon_checkout(p_actor uuid,p_campus uuid,p_key text,p_legacy_key text,p_guest_email text DEFAULT NULL,p_guest_phone text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE saved public.orders%rowtype;result jsonb;key text;contact text;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' OR p_key IS NULL OR p_key!~'^v2:[0-9a-f]{64}$' OR p_campus IS NULL
  OR p_legacy_key IS NULL OR length(p_legacy_key) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'checkout_forbidden' USING ERRCODE='42501'; END IF;
 IF p_actor IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_actor AND is_active) THEN RAISE EXCEPTION 'checkout_forbidden' USING ERRCODE='42501'; END IF;
 IF p_actor IS NULL AND (nullif(btrim(p_guest_email),'') IS NULL OR nullif(btrim(p_guest_phone),'') IS NULL) THEN RAISE EXCEPTION 'checkout_forbidden' USING ERRCODE='42501'; END IF;
 contact:=CASE WHEN p_actor IS NULL THEN md5(lower(btrim(p_guest_email))||':'||btrim(p_guest_phone)) END;
 FOR key IN SELECT DISTINCT k FROM unnest(ARRAY[p_key,p_legacy_key]) k ORDER BY k LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('hg-checkout-intent:'||key,0));
 END LOOP;
 SELECT * INTO saved FROM public.orders WHERE idempotency_key IN (p_key,p_legacy_key) ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
 IF FOUND THEN
  IF saved.campus_id IS DISTINCT FROM p_campus OR saved.user_id IS DISTINCT FROM p_actor
   OR (p_actor IS NULL AND (lower(btrim(saved.guest_email::text)) IS DISTINCT FROM lower(btrim(p_guest_email)) OR btrim(saved.guest_phone) IS DISTINCT FROM btrim(p_guest_phone))) THEN
   RAISE EXCEPTION 'checkout_forbidden' USING ERRCODE='42501';
  END IF;
  IF saved.status::text NOT IN ('cancelled','refunded') THEN
   IF saved.payment_status::text IN ('paid','partially_refunded','refunded') THEN
    RETURN jsonb_build_object('state','paid','order',jsonb_build_object('id',saved.id,'payment_status',saved.payment_status,'status',saved.status,'claim_token',CASE WHEN p_actor IS NULL THEN saved.claim_token END));
   END IF;
   IF saved.payment_status::text NOT IN ('pending','failed') OR saved.status::text<>'received' THEN RAISE EXCEPTION 'checkout_not_cancellable'; END IF;
   IF p_actor IS NOT NULL THEN
    result:=public.hg_refund_order_atomic(saved.id,p_actor,'abandon-checkout',NULL,'Customer started a new checkout',true);
    IF result->>'success' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'checkout_release_failed'; END IF;
   ELSE
    IF coalesce(saved.wallet_amount_used,0)<>0 OR coalesce(saved.hp_redeemed,0)<>0 OR saved.order_lock_id IS NOT NULL OR saved.promo_code_id IS NOT NULL OR saved.redemption_id IS NOT NULL THEN RAISE EXCEPTION 'checkout_needs_assistance'; END IF;
    UPDATE public.orders SET status='cancelled',payment_status='failed',updated_at=now() WHERE id=saved.id;
   END IF;
  END IF;
 END IF;
 -- This scoped key also closes the unknown-response race. A request that has
 -- not committed yet cannot subsequently create an order for the old intent.
 INSERT INTO hg_internal.checkout_intent_closures(intent_key,owner_id,campus_id,guest_contact_hash) VALUES(p_key,p_actor,p_campus,contact) ON CONFLICT DO NOTHING;
 IF saved.id IS NOT NULL AND saved.idempotency_key=p_legacy_key THEN
  INSERT INTO hg_internal.checkout_intent_closures(intent_key,owner_id,campus_id,guest_contact_hash) VALUES(p_legacy_key,p_actor,p_campus,contact) ON CONFLICT DO NOTHING;
 END IF;
 RETURN jsonb_build_object('state','closed','order_id',saved.id);
END $$;
REVOKE ALL ON FUNCTION public.hg_abandon_checkout(uuid,uuid,text,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_abandon_checkout(uuid,uuid,text,text,text,text) TO service_role;
NOTIFY pgrst,'reload schema';
