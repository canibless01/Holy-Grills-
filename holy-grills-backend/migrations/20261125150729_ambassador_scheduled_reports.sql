-- Personal progress plus campus-team counts only; never financial reporting.
CREATE TABLE hg_internal.ambassador_report_receipts (
 user_id uuid NOT NULL REFERENCES public.profiles(id), campus_id uuid NOT NULL REFERENCES public.campuses(id),
 kind text NOT NULL CHECK(kind IN ('weekly','monthly')), period_start date NOT NULL,
 notification_id uuid NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,kind,period_start)
);
ALTER TABLE hg_internal.ambassador_report_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.ambassador_report_receipts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON hg_internal.ambassador_report_receipts TO service_role;

CREATE FUNCTION public.hg_ambassador_mail_data(p_campus uuid,p_kind text,p_start date)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE actor uuid; data jsonb; people jsonb; team jsonb; tiers jsonb; last_day date;
BEGIN
 IF p_start IS NULL OR p_kind NOT IN ('weekly','monthly') OR p_kind IS NULL
 OR (p_kind='weekly' AND extract(isodow FROM p_start)<>1)
 OR (p_kind='monthly' AND extract(day FROM p_start)<>1) THEN RETURN '{"error":"invalid"}'; END IF;
 last_day:=CASE WHEN p_kind='weekly' THEN p_start+7 ELSE (p_start+interval '1 month')::date END;
 IF last_day>(now() AT TIME ZONE 'Africa/Lagos')::date THEN RETURN '{"error":"incomplete"}'; END IF;
 IF NOT EXISTS(SELECT 1 FROM campuses WHERE id=p_campus AND is_active) THEN RETURN '{"error":"forbidden"}'; END IF;
 SELECT id INTO actor FROM profiles WHERE is_active AND (role::text='super_admin' OR (role::text='admin' AND campus_id=p_campus)) ORDER BY (role::text='admin') DESC,id LIMIT 1;
 IF actor IS NULL THEN RETURN '{"error":"no_campus_admin"}'; END IF;
 data:=public.hg_ambassador_insights(actor,p_campus,to_char(CASE WHEN p_kind='weekly' THEN last_day-1 ELSE p_start END,'YYYY-MM'),p_start-(extract(isodow FROM p_start)::integer-1));
 IF data->>'error' IS NOT NULL THEN RETURN data; END IF;
 WITH owners AS (
  SELECT (x->'profile'->>'id')::uuid AS user_id,x->'profile'->>'nickname' AS nickname,x->'profile'->>'full_name' AS name,
   x->CASE WHEN p_kind='weekly' THEN 'week' ELSE 'month' END AS metrics,x->'month' AS month_metrics
  FROM jsonb_array_elements(data->'ambassadors') x
 ), rows AS (
 SELECT o.user_id,o.nickname,o.name,t.name AS current_tier,
  jsonb_build_object('signups',coalesce((o.metrics->>'signups')::int,0),'orders',coalesce((o.metrics->>'orders')::int,0),'shared_count',coalesce((o.metrics->>'shared_count')::int,0),'assigned_count',coalesce((o.metrics->>'assigned_count')::int,0)) AS progress,
  jsonb_build_object('signups',coalesce((o.month_metrics->>'signups')::int,0),'orders',coalesce((o.month_metrics->>'orders')::int,0),'shared_count',coalesce((o.month_metrics->>'shared_count')::int,0),'monthly_share_target',coalesce((o.month_metrics->>'monthly_share_target')::int,0)) AS month_progress
 FROM owners o JOIN profiles p ON p.id=o.user_id AND p.campus_id=p_campus AND p.is_active AND p.role::text='student'
 LEFT JOIN hp_tiers t ON t.id=p.current_tier_id AND t.is_active AND (t.campus_id=p_campus OR t.campus_id IS NULL)
 ) SELECT coalesce(jsonb_agg(to_jsonb(rows)),'[]') INTO people FROM rows;
 SELECT jsonb_build_object('ambassadors',count(*),'signups',coalesce(sum((x->'progress'->>'signups')::int),0),'orders',coalesce(sum((x->'progress'->>'orders')::int),0),'shared_count',coalesce(sum((x->'progress'->>'shared_count')::int),0)) INTO team FROM jsonb_array_elements(people) x;
 SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') INTO tiers FROM (SELECT x->>'current_tier' AS tier,count(*) AS members FROM jsonb_array_elements(people) x GROUP BY x->>'current_tier' ORDER BY x->>'current_tier') t;
 RETURN jsonb_build_object('kind',p_kind,'month',data->>'month','period_start',p_start,'period_end',last_day-1,'campus_id',p_campus,'campus_name',(SELECT name FROM campuses WHERE id=p_campus),'people',people,'team',team,'tiers',tiers);
END $$;

CREATE FUNCTION public.hg_queue_ambassador_report(p_user uuid,p_campus uuid,p_kind text,p_start date,p_title text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE nid uuid; count_rows integer;
BEGIN
 IF p_kind IS NULL OR p_kind NOT IN ('weekly','monthly') OR p_start IS NULL
 OR (p_kind='weekly' AND (extract(isodow FROM p_start)<>1 OR p_start+7>(now() AT TIME ZONE 'Africa/Lagos')::date))
 OR (p_kind='monthly' AND (extract(day FROM p_start)<>1 OR p_start+interval '1 month'>(now() AT TIME ZONE 'Africa/Lagos')::date))
 OR coalesce(length(trim(p_title)),0) NOT BETWEEN 1 AND 200 OR coalesce(length(trim(p_body)),0) NOT BETWEEN 1 AND 12000 THEN RETURN '{"error":"invalid"}'; END IF;
 IF NOT EXISTS(SELECT 1 FROM ambassadors a JOIN profiles p ON p.id=a.profile_id JOIN campuses c ON c.id=a.campus_id
 LEFT JOIN notification_preferences n ON n.user_id=p.id WHERE p.id=p_user AND p.campus_id=p_campus AND a.campus_id=p_campus AND a.status='active'
 AND p.is_active AND p.role::text='student' AND c.is_active AND length(trim(coalesce(p.email,'')))>3
 AND p.email_notifications IS DISTINCT FROM false AND n.email_enabled IS DISTINCT FROM false AND n.promotions IS DISTINCT FROM false)
 THEN RETURN '{"skipped":true}'; END IF;
 nid:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8',p_user||':ambassador-report:'||p_kind||':'||p_start);
 INSERT INTO hg_internal.ambassador_report_receipts(user_id,campus_id,kind,period_start,notification_id) VALUES(p_user,p_campus,p_kind,p_start,nid) ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS count_rows=ROW_COUNT;
 IF count_rows=0 THEN RETURN '{"duplicate":true}'; END IF;
 INSERT INTO notifications(id,user_id,campus_id,title,body,type,channel,action_url,metadata)
 VALUES(nid,p_user,p_campus,p_title,p_body,'ambassador_progress_report','email','/dashboard',jsonb_build_object('_dispatch_version',1,'report_kind',p_kind,'period_start',p_start,'report_campus_id',p_campus));
 RETURN jsonb_build_object('queued',true,'notification_id',nid);
END $$;

CREATE FUNCTION public.hg_ambassador_report_notice_valid(p_user uuid,p_campus uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM ambassadors a JOIN profiles p ON p.id=a.profile_id JOIN campuses c ON c.id=a.campus_id
 WHERE a.profile_id=p_user AND a.campus_id=p_campus AND p.campus_id=p_campus AND a.status='active' AND p.is_active AND p.role::text='student' AND c.is_active)
$$;
REVOKE ALL ON FUNCTION public.hg_ambassador_mail_data(uuid,text,date),public.hg_queue_ambassador_report(uuid,uuid,text,date,text,text),public.hg_ambassador_report_notice_valid(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_mail_data(uuid,text,date),public.hg_queue_ambassador_report(uuid,uuid,text,date,text,text),public.hg_ambassador_report_notice_valid(uuid,uuid) TO service_role;

CREATE FUNCTION public.hg_due_ambassador_report_campuses(p_kind text,p_start date)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT coalesce(jsonb_agg(to_jsonb(c)),'[]') FROM (
 SELECT DISTINCT a.campus_id FROM ambassadors a JOIN profiles p ON p.id=a.profile_id JOIN campuses c ON c.id=a.campus_id
 LEFT JOIN notification_preferences n ON n.user_id=p.id
 WHERE p_kind IN ('weekly','monthly') AND p_start IS NOT NULL AND a.status='active' AND p.is_active AND p.role::text='student' AND c.is_active AND p.campus_id=a.campus_id
 AND length(trim(coalesce(p.email,'')))>3 AND p.email_notifications IS DISTINCT FROM false AND n.email_enabled IS DISTINCT FROM false AND n.promotions IS DISTINCT FROM false
 AND NOT EXISTS(SELECT 1 FROM hg_internal.ambassador_report_receipts r WHERE r.user_id=p.id AND r.kind=p_kind AND r.period_start=p_start)
 ORDER BY a.campus_id) c
$$;
REVOKE ALL ON FUNCTION public.hg_due_ambassador_report_campuses(text,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_due_ambassador_report_campuses(text,date) TO service_role;
