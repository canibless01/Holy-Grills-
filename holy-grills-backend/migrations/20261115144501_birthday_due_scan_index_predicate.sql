-- Keep the birthday-only scan compatible with its active-student partial index.
CREATE OR REPLACE FUNCTION public.hg_due_birthdays(p_limit integer DEFAULT 100) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') FROM (
 SELECT p.id,p.campus_id FROM public.profiles p JOIN public.campuses c ON c.id=p.campus_id AND c.is_active
 WHERE p.is_active AND p.role='student'::public.user_role AND extract(month FROM p.date_of_birth)=extract(month FROM now() AT TIME ZONE 'Africa/Lagos') AND extract(day FROM p.date_of_birth)=extract(day FROM now() AT TIME ZONE 'Africa/Lagos')
 AND NOT EXISTS(SELECT 1 FROM hg_internal.birthday_celebrations b WHERE b.user_id=p.id AND b.year=extract(year FROM now() AT TIME ZONE 'Africa/Lagos')::integer)
 ORDER BY p.id LIMIT least(greatest(coalesce(p_limit,100),1),200))x
$$;

CREATE OR REPLACE FUNCTION public.hg_queue_birthday_reports(p_campus uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;campus uuid;people jsonb;n integer:=0;
BEGIN
 FOR campus IN SELECT c.id FROM public.campuses c JOIN public.system_settings s ON s.campus_id=c.id AND s.key='campus_operations_email' AND NOT s.is_public WHERE c.is_active AND (p_campus IS NULL OR c.id=p_campus) AND coalesce((s.value->>'birthday_report')::boolean,true) LOOP
  SELECT coalesce(jsonb_agg(jsonb_build_object('name',coalesce(nullif(btrim(p.nickname),''),p.full_name),'date',to_char(p.date_of_birth,'DD Mon'),'phone',p.phone,'faculty',p.faculty,'department',p.department) ORDER BY extract(day FROM p.date_of_birth),p.id),'[]') INTO people FROM public.profiles p WHERE p.campus_id=campus AND p.is_active AND p.role='student'::public.user_role AND extract(month FROM p.date_of_birth)=extract(month FROM today);
  PERFORM public.hg_queue_operations_email(campus,'birthday_report',to_char(today,'YYYY-MM'),jsonb_build_object('month',to_char(today,'FMMonth YYYY'),'people',people,'count',jsonb_array_length(people)));
  n:=n+1;
 END LOOP;
 RETURN jsonb_build_object('campuses',n,'month',to_char(today,'YYYY-MM'));
END$$;
