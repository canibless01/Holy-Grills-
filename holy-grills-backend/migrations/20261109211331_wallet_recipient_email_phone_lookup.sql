-- Exact matching only; no name search, contact listing, or money-path changes.
CREATE INDEX wallet_transfer_email_lookup ON public.profiles(campus_id,lower(btrim(email::text))) WHERE is_active;
CREATE INDEX wallet_transfer_phone_lookup ON public.profiles(campus_id,(CASE WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^2340[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^0[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^[0-9]{10}$' THEN '234'||regexp_replace(phone,'[+() .-]','','g') ELSE regexp_replace(phone,'[+() .-]','','g') END)) WHERE is_active;
DO $migration$
DECLARE definition text;first_pos integer;last_pos integer;replacement text;
BEGIN
 definition:=pg_get_functiondef('public.hg_wallet_transfer(text,uuid,uuid,jsonb)'::regprocedure);
 first_pos:=strpos(definition,' ELSIF p_action=''lookup'' THEN');
 last_pos:=strpos(definition,' ELSIF p_action<>''send'' THEN');
 IF first_pos=0 OR last_pos<=first_pos THEN RAISE EXCEPTION 'Unexpected wallet transfer lookup boundary'; END IF;
 replacement:=$lookup$ ELSIF p_action='lookup' THEN
  code:=btrim(coalesce(p_data->>'value',p_data->>'code'));
  IF coalesce(p_data->>'lookup_type','code')='code' THEN
   code:=upper(code);
   IF code IS NULL OR code!~'^[A-Z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'invalid_recipient_code'; END IF;
  ELSIF p_data->>'lookup_type'='email' THEN
   code:=lower(code);
   IF code IS NULL OR length(code)>254 OR code!~'^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSIF p_data->>'lookup_type'='phone' THEN
   IF code IS NULL OR code!~'^[1-9][0-9]{7,14}$' THEN RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  ELSE RAISE EXCEPTION 'invalid_recipient_identifier'; END IF;
  SELECT array_agg(id) INTO ids FROM (
   SELECT id FROM public.profiles WHERE is_active AND campus_id=s.campus_id AND
    CASE coalesce(p_data->>'lookup_type','code')
     WHEN 'code' THEN upper(referral_code)=code
     WHEN 'email' THEN lower(btrim(email::text))=code
     WHEN 'phone' THEN (CASE WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^2340[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^0[0-9]{10}$' THEN '234'||right(regexp_replace(phone,'[+() .-]','','g'),10) WHEN regexp_replace(phone,'[+() .-]','','g') ~ '^[0-9]{10}$' THEN '234'||regexp_replace(phone,'[+() .-]','','g') ELSE regexp_replace(phone,'[+() .-]','','g') END)=code
     ELSE false END LIMIT 2) candidates;
  IF coalesce(cardinality(ids),0)=0 THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  IF cardinality(ids)>1 THEN RAISE EXCEPTION 'recipient_ambiguous'; END IF;
  SELECT * INTO r FROM public.profiles WHERE id=ids[1];
  IF r.id=s.id THEN RAISE EXCEPTION 'self_transfer'; END IF;
  IF coalesce(r.referral_code,'')!~'^[A-Za-z0-9_-]{3,80}$' THEN RAISE EXCEPTION 'recipient_unavailable'; END IF;
  RETURN jsonb_build_object('id',r.id,'name',left(coalesce(nullif(btrim(r.nickname),''),nullif(btrim(r.full_name),''),'Campus member'),100),'code',r.referral_code);$lookup$;
 definition:=substring(definition,1,first_pos-1)||replacement||substring(definition,last_pos);
 EXECUTE definition;
END $migration$;
