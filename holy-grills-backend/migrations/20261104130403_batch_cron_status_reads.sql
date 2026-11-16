-- One API round-trip replaces one audit-log request for each job.
CREATE INDEX IF NOT EXISTS admin_audit_logs_cron_job_recent_idx
 ON public.admin_audit_logs(entity_id,created_at DESC,id DESC) WHERE entity_type='cron_jobs';
CREATE FUNCTION public.hg_cron_execution_summary(p_jobs text[])
RETURNS TABLE(job text,last_run jsonb,last_success jsonb)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $fn$
 SELECT requested.job,to_jsonb(latest),to_jsonb(success)
 FROM unnest(p_jobs) requested(job)
 LEFT JOIN LATERAL(
  SELECT entity_id,action,created_at,after_value,actor_id FROM public.admin_audit_logs
  WHERE entity_type='cron_jobs' AND entity_id=requested.job ORDER BY created_at DESC,id DESC LIMIT 1
 ) latest ON true
 LEFT JOIN LATERAL(
  SELECT entity_id,action,created_at,after_value,actor_id FROM public.admin_audit_logs
  WHERE entity_type='cron_jobs' AND entity_id=requested.job AND action='scheduled_execution_success'
  ORDER BY created_at DESC,id DESC LIMIT 1
 ) success ON true;
$fn$;
REVOKE ALL ON FUNCTION public.hg_cron_execution_summary(text[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_cron_execution_summary(text[]) TO service_role;
