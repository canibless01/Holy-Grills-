-- Reuse the existing free-side ledger; one deterministic receipt per account.
-- Configuration is scoped by the account's campus, falling back to global.
INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
VALUES ('signup_free_side_config','{"enabled":true,"credits":1,"validity_days":60}'::jsonb,
        'New-account welcome free-side credit configuration.',true,NULL)
ON CONFLICT (key) WHERE campus_id IS NULL DO NOTHING;
INSERT INTO public.system_settings(key,value,description,is_public,campus_id)
VALUES ('signup_free_side_cutover',to_jsonb(clock_timestamp()),
        'Accounts created before this rollout are not eligible for signup free-side credits.',false,NULL)
ON CONFLICT (key) WHERE campus_id IS NULL DO NOTHING;
-- Retire future physical first-order gifts; existing gift records/items remain.
UPDATE public.system_settings SET value='false'::jsonb,updated_at=now()
 WHERE key='first_order_gift_enabled' AND value IS DISTINCT FROM 'false'::jsonb;

CREATE OR REPLACE FUNCTION public.hg_grant_signup_free_side_atomic(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO public AS $function$
DECLARE
 v_profile public.profiles%ROWTYPE; v_credit public.free_side_credits%ROWTYPE;
 v_config jsonb; v_cutover timestamptz; v_account_created timestamptz;
 v_credits integer; v_days integer; v_id uuid:=md5('hg-signup-free-side:'||p_user_id::text)::uuid;
 v_now timestamptz:=clock_timestamp();
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('granted',false,'reason','profile_unavailable'); END IF;
 -- Do not lock or update an existing credit: consumption may hold that row
 -- before acquiring the wallet/profile locks. A retry never refills its balance.
 SELECT * INTO v_credit FROM public.free_side_credits WHERE id=v_id;
 IF FOUND THEN
  IF v_credit.user_id IS DISTINCT FROM p_user_id OR v_credit.source<>'signup' THEN
   RETURN jsonb_build_object('error','receipt_conflict');
  END IF;
  RETURN jsonb_build_object('granted',false,'idempotent',true,'credit_id',v_credit.id,
                           'credits_remaining',v_credit.credits_remaining,'expires_at',v_credit.expires_at);
 END IF;
 IF v_profile.role::text<>'student' OR v_profile.campus_id IS NULL THEN
  RETURN jsonb_build_object('granted',false,'reason','account_ineligible');
 END IF;
 SELECT (value#>>'{}')::timestamptz INTO v_cutover FROM public.system_settings
  WHERE key='signup_free_side_cutover' AND campus_id IS NULL;
 IF NOT FOUND OR v_cutover IS NULL THEN RETURN jsonb_build_object('error','configuration'); END IF;
 SELECT created_at INTO v_account_created FROM auth.users WHERE id=p_user_id;
 IF v_account_created IS NULL OR v_account_created<v_cutover THEN
  RETURN jsonb_build_object('granted',false,'reason','before_rollout');
 END IF;
 SELECT value INTO v_config FROM public.system_settings WHERE key='signup_free_side_config'
  AND (campus_id=v_profile.campus_id OR campus_id IS NULL)
  ORDER BY (campus_id IS NOT NULL) DESC LIMIT 1;
 IF NOT FOUND OR jsonb_typeof(v_config)<>'object' OR (SELECT count(*) FROM jsonb_object_keys(v_config))<>3
    OR jsonb_typeof(v_config->'enabled') IS DISTINCT FROM 'boolean'
    OR jsonb_typeof(v_config->'credits') IS DISTINCT FROM 'number'
    OR jsonb_typeof(v_config->'validity_days') IS DISTINCT FROM 'number'
    OR coalesce(v_config->>'credits','') !~ '^[0-9]{1,2}$'
    OR coalesce(v_config->>'validity_days','') !~ '^[0-9]{1,3}$' THEN
  RETURN jsonb_build_object('error','configuration');
 END IF;
 v_credits:=(v_config->>'credits')::integer;v_days:=(v_config->>'validity_days')::integer;
 IF v_credits NOT BETWEEN 1 AND 10 OR v_days NOT BETWEEN 1 AND 365 THEN
  RETURN jsonb_build_object('error','configuration');
 END IF;
 IF NOT (v_config->>'enabled')::boolean THEN RETURN jsonb_build_object('granted',false,'reason','disabled'); END IF;
 INSERT INTO public.free_side_credits(id,user_id,credits_remaining,source,campus_id,created_at,expires_at)
 VALUES(v_id,p_user_id,v_credits,'signup',v_profile.campus_id,v_now,v_now+make_interval(days=>v_days))
 RETURNING * INTO v_credit;
 RETURN jsonb_build_object('granted',true,'idempotent',false,'credit_id',v_credit.id,
                          'credits_remaining',v_credit.credits_remaining,'expires_at',v_credit.expires_at);
EXCEPTION WHEN OTHERS THEN
 -- Configuration errors/failed inserts cannot leave a partial or duplicate grant.
 RETURN jsonb_build_object('error','welcome_credit_unavailable','debug_code',SQLSTATE);
END;
$function$;
REVOKE ALL ON FUNCTION public.hg_grant_signup_free_side_atomic(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_grant_signup_free_side_atomic(uuid) TO service_role;
