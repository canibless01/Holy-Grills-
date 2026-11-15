CREATE TABLE hg_internal.birthday_celebrations (
 id uuid PRIMARY KEY,user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
 campus_id uuid NOT NULL REFERENCES public.campuses(id),year integer NOT NULL,hp_awarded integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(user_id,year)
);
ALTER TABLE hg_internal.birthday_celebrations ENABLE ROW LEVEL SECURITY;
CREATE POLICY birthday_celebrations_service ON hg_internal.birthday_celebrations FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.birthday_celebrations FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.birthday_celebrations TO service_role;
CREATE INDEX profiles_active_student_birthday ON public.profiles((extract(month FROM date_of_birth)),(extract(day FROM date_of_birth)),campus_id,id) WHERE is_active AND role='student'::public.user_role;
CREATE FUNCTION public.hg_due_birthdays(p_limit integer DEFAULT 100) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') FROM (
 SELECT p.id,p.campus_id FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id AND c.is_active
 WHERE p.is_active AND p.role::text='student' AND extract(month FROM p.date_of_birth)=extract(month FROM now() AT TIME ZONE 'Africa/Lagos') AND extract(day FROM p.date_of_birth)=extract(day FROM now() AT TIME ZONE 'Africa/Lagos')
 AND NOT EXISTS(SELECT 1 FROM hg_internal.birthday_celebrations b WHERE b.user_id=p.id AND b.year=extract(year FROM now() AT TIME ZONE 'Africa/Lagos')::integer)
 ORDER BY p.id LIMIT least(greatest(coalesce(p_limit,100),1),200))x
$$;
CREATE FUNCTION public.hg_process_birthday(p_user uuid,p_hp integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person public.profiles%rowtype;peer public.profiles%rowtype;prefs public.notification_preferences%rowtype;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;ref uuid;ch text;notice uuid;meta jsonb;body text;label text;result jsonb;awarded integer:=0;legacy_count integer;enabled boolean;recipient uuid;kind text;link text;title text;
BEGIN
 IF p_hp IS NULL OR p_hp<0 THEN RAISE EXCEPTION 'Invalid birthday HP plan';END IF;
 SELECT p.* INTO person FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id AND c.is_active WHERE p.id=p_user AND p.is_active AND p.role::text='student' FOR UPDATE OF p;
 IF NOT FOUND OR to_char(person.date_of_birth,'MM-DD') IS DISTINCT FROM to_char(today,'MM-DD') THEN RETURN jsonb_build_object('skipped',true);END IF;
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:birthday:'||p_user||':'||extract(year FROM today));
 IF EXISTS(SELECT 1 FROM hg_internal.birthday_celebrations WHERE id=ref) THEN RETURN jsonb_build_object('replayed',true);END IF;
 SELECT count(*),coalesce(sum(amount) FILTER(WHERE status='active'),0) INTO legacy_count,awarded FROM public.hp_transactions WHERE user_id=p_user AND reference_type='birthday' AND type='earn' AND created_at>=date_trunc('year',today)::timestamp AT TIME ZONE 'Africa/Lagos';
 IF legacy_count=0 AND p_hp>0 THEN
  result:=public.record_hp_transaction_atomic(p_user,p_hp,'earn','active','birthday','birthday',ref,null,'Birthday gift',person.campus_id);
  IF result ? 'error' THEN RAISE EXCEPTION 'Birthday reward unavailable';END IF;
  awarded:=p_hp;PERFORM public.increment_monthly_hp_tracker(p_user,to_char(today,'YYYY-MM'),awarded);
 END IF;
 INSERT INTO hg_internal.birthday_celebrations(id,user_id,campus_id,year,hp_awarded) VALUES(ref,p_user,person.campus_id,extract(year FROM today)::integer,awarded);
 label:=coalesce(nullif(btrim(person.nickname),''),nullif(btrim(person.full_name),''),'Your campus friend');
 title:='Happy birthday, '||label||'!';
 body:=CASE WHEN awarded>0 THEN 'A little birthday fire: '||awarded||' HP is in your active balance. Here''s to good food and good people.' ELSE 'Your day, your people. Happy birthday from all of us at Holy Grills!' END;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=person.id;
 IF prefs.hp_updates IS DISTINCT FROM false THEN
  FOREACH ch IN ARRAY ARRAY['in_app','push','email'] LOOP
   IF ch='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) OR ch='email' AND (person.email_notifications IS FALSE OR prefs.email_enabled IS FALSE) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5(ref,'birthday_bonus:'||ch);
   meta:=jsonb_build_object('_dispatch_version',1,'reference_type','birthday_celebration','reference_id',ref,'celebrant_id',person.id,'birthday_date',today,'hp_awarded',awarded);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata) VALUES(notice,person.id,'birthday_bonus',title,body,ch,'/wallet',person.campus_id,ref,meta) ON CONFLICT DO NOTHING;
  END LOOP;
 END IF;
 SELECT is_active INTO enabled FROM public.feature_flags WHERE feature_name='birthday_celebrations' AND(campus_id=person.campus_id OR campus_id IS NULL) ORDER BY campus_id IS NOT NULL DESC LIMIT 1;
 IF enabled AND person.referral_code ~ '^[A-Za-z0-9_-]{3,80}$' AND (person.department_id IS NOT NULL OR nullif(btrim(person.department),'') IS NOT NULL) THEN
  link:='/wallet?gift_to='||person.referral_code||'&birthday='||today;
  FOR peer IN SELECT p.* FROM public.profiles p WHERE p.is_active AND p.role::text='student' AND p.campus_id=person.campus_id AND p.id<>person.id AND
   ((person.department_id IS NOT NULL AND p.department_id=person.department_id) OR (person.department_id IS NULL AND p.department_id IS NULL AND lower(btrim(p.department))=lower(btrim(person.department)))) LOOP
   SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=peer.id;
   IF prefs.hp_updates IS FALSE THEN CONTINUE;END IF;
   FOREACH ch IN ARRAY ARRAY['in_app','push'] LOOP
    IF ch='push' AND (peer.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
    notice:=extensions.uuid_generate_v5(ref,'birthday_blast:'||peer.id||':'||ch);
    meta:=jsonb_build_object('_dispatch_version',1,'reference_type','birthday_celebration','reference_id',ref,'celebrant_id',person.id,'birthday_date',today);
    INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
     VALUES(notice,peer.id,'birthday_blast','It''s '||label||'''s birthday!','Your department has someone to celebrate. Wish '||label||' well, or send a little wallet money or HP love.',ch,link,person.campus_id,ref,meta) ON CONFLICT DO NOTHING;
    UPDATE public.notification_deliveries SET dispatch=jsonb_set(dispatch,'{expires_at}',to_jsonb((today+1)::timestamp AT TIME ZONE 'Africa/Lagos')) WHERE id=notice;
   END LOOP;
  END LOOP;
 END IF;
 RETURN jsonb_build_object('processed',true,'reference_id',ref,'hp_awarded',awarded,'legacy_adopted',legacy_count>0);
END$$;
ALTER TABLE hg_internal.operations_emails DROP CONSTRAINT operations_emails_kind_check;
ALTER TABLE hg_internal.operations_emails ADD CONSTRAINT operations_emails_kind_check CHECK(kind IN('paid_order','abandoned_cart','daily_report','weekly_report','birthday_report'));
CREATE FUNCTION public.hg_queue_birthday_reports(p_campus uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;campus uuid;people jsonb;n integer:=0;
BEGIN
 FOR campus IN SELECT c.id FROM public.campuses c JOIN public.system_settings s ON s.campus_id=c.id AND s.key='campus_operations_email' AND NOT s.is_public WHERE c.is_active AND (p_campus IS NULL OR c.id=p_campus) AND coalesce((s.value->>'birthday_report')::boolean,true) LOOP
  SELECT coalesce(jsonb_agg(jsonb_build_object('name',coalesce(nullif(btrim(p.nickname),''),p.full_name),'date',to_char(p.date_of_birth,'DD Mon'),'phone',p.phone,'faculty',p.faculty,'department',p.department) ORDER BY extract(day FROM p.date_of_birth),p.id),'[]') INTO people FROM public.profiles p WHERE p.campus_id=campus AND p.is_active AND p.role::text='student' AND extract(month FROM p.date_of_birth)=extract(month FROM today);
  PERFORM public.hg_queue_operations_email(campus,'birthday_report',to_char(today,'YYYY-MM'),jsonb_build_object('month',to_char(today,'FMMonth YYYY'),'people',people,'count',jsonb_array_length(people)));
  n:=n+1;
 END LOOP;
 RETURN jsonb_build_object('campuses',n,'month',to_char(today,'YYYY-MM'));
END$$;
REVOKE ALL ON FUNCTION public.hg_due_birthdays(integer),public.hg_process_birthday(uuid,integer),public.hg_queue_birthday_reports(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_due_birthdays(integer),public.hg_process_birthday(uuid,integer),public.hg_queue_birthday_reports(uuid) TO service_role;
INSERT INTO public.feature_flags(feature_name,is_active,description,campus_id) SELECT 'birthday_celebrations',true,'Department birthday notices with same-campus gift links',NULL WHERE NOT EXISTS(SELECT 1 FROM public.feature_flags WHERE feature_name='birthday_celebrations' AND campus_id IS NULL);

CREATE OR REPLACE FUNCTION public.hg_queue_operations_email(p_campus uuid, p_kind text, p_reference text, p_payload jsonb DEFAULT '{}'::jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE cfg jsonb;recipient text;flag text;
BEGIN
 flag:=CASE p_kind WHEN 'paid_order' THEN 'paid_order_alerts' WHEN 'abandoned_cart' THEN 'abandoned_cart_alerts' ELSE p_kind END;
 SELECT value INTO cfg FROM public.system_settings WHERE key='campus_operations_email' AND campus_id=p_campus AND NOT is_public;
 IF cfg IS NULL OR NOT coalesce((cfg->>flag)::boolean,p_kind='birthday_report') THEN RETURN; END IF;
 FOR recipient IN SELECT DISTINCT lower(btrim(v)) FROM jsonb_array_elements_text(cfg->'recipients') v LOOP
  INSERT INTO hg_internal.operations_emails(campus_id,kind,reference,recipient,payload)
   VALUES(p_campus,p_kind,p_reference,recipient,p_payload) ON CONFLICT DO NOTHING;
 END LOOP;
END $function$

;
CREATE OR REPLACE FUNCTION public.hg_validate_operations_email_setting()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'public'
AS $function$
DECLARE email text; k text;
BEGIN
 IF NEW.key='campus_cart_recovery' THEN
  IF NEW.campus_id IS NULL OR NEW.is_public IS DISTINCT FROM false OR jsonb_typeof(NEW.value)<>'object'
    OR coalesce(NEW.value->>'initial_minutes','')!~'^[0-9]+$' OR (NEW.value->>'initial_minutes')::integer NOT BETWEEN 10 AND 1440
    OR coalesce(NEW.value->>'repeat_minutes','')!~'^[0-9]+$' OR (NEW.value->>'repeat_minutes')::integer NOT BETWEEN 30 AND 1440
    OR coalesce(NEW.value->>'max_hours','')!~'^[0-9]+$' OR (NEW.value->>'max_hours')::integer NOT BETWEEN 1 AND 48 THEN RAISE EXCEPTION 'Invalid private campus cart recovery timing'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.key<>'campus_operations_email' THEN RETURN NEW; END IF;
 IF NEW.campus_id IS NULL OR NEW.is_public IS DISTINCT FROM false OR jsonb_typeof(NEW.value)<>'object'
  OR jsonb_typeof(NEW.value->'recipients') IS DISTINCT FROM 'array'
  OR jsonb_array_length(NEW.value->'recipients')>5 THEN RAISE EXCEPTION 'Operations email needs a private campus setting and up to five recipients'; END IF;
 FOR email IN SELECT jsonb_array_elements_text(NEW.value->'recipients') LOOP
  IF email IS NULL OR length(email)>254 OR email !~* '^[a-z0-9.!#$%&''*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}$' THEN RAISE EXCEPTION 'Invalid operations email recipient'; END IF;
 END LOOP;
 FOREACH k IN ARRAY ARRAY['paid_order_alerts','abandoned_cart_alerts','daily_report','weekly_report'] LOOP
  IF jsonb_typeof(NEW.value->k) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Operations email switches must be boolean'; END IF;
 END LOOP;
 IF coalesce(NEW.value->>'abandoned_minutes','') !~ '^[0-9]+$' OR (NEW.value->>'abandoned_minutes')::integer NOT BETWEEN 30 AND 1440 THEN RAISE EXCEPTION 'Abandonment delay must be 30 to 1440 minutes'; END IF;
 IF NEW.value ? 'daily_report_time' AND (jsonb_typeof(NEW.value->'daily_report_time') IS DISTINCT FROM 'string' OR NEW.value->>'daily_report_time' !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$') THEN RAISE EXCEPTION 'Daily report time must be HH:MM in Nigeria time'; END IF;
 IF NEW.value ? 'birthday_report' AND jsonb_typeof(NEW.value->'birthday_report') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Birthday report switch must be boolean';END IF;
 RETURN NEW;
END $function$

;
CREATE FUNCTION public.hg_birthday_recipient(p_actor uuid,p_code text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('id',p.id,'name',coalesce(nullif(btrim(p.nickname),''),p.full_name),'code',p.referral_code,'department',p.department)
 FROM public.profiles a JOIN public.profiles p ON p.campus_id=a.campus_id AND p.role::text='student' AND p.is_active
 WHERE a.id=p_actor AND a.is_active AND a.role::text='student' AND upper(p.referral_code)=upper(p_code)
 AND to_char(p.date_of_birth,'MM-DD')=to_char(now() AT TIME ZONE 'Africa/Lagos','MM-DD')
 AND coalesce((SELECT is_active FROM public.feature_flags WHERE feature_name='birthday_celebrations' AND (campus_id=a.campus_id OR campus_id IS NULL) ORDER BY campus_id IS NOT NULL DESC LIMIT 1),false)
 LIMIT 1
$$;
REVOKE ALL ON FUNCTION public.hg_birthday_recipient(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_birthday_recipient(uuid,text) TO service_role;
