-- A paused campus must not occupy all 50 renewal slots ahead of active campuses.
-- Long-overdue renewals still enter the scan so consent can be stopped safely.
DO $fairness$
DECLARE body text;needle text:=$old$WHERE auto_renew AND paid_until<=now() ORDER BY paid_until,id LIMIT 50$old$;
 replacement text:=$new$WHERE auto_renew AND paid_until<=now()
 AND (paid_until<now()-interval '48 hours' OR hg_internal.delivery_pass_sale_enabled(campus_id))
 ORDER BY paid_until,id LIMIT 50$new$;
BEGIN
 SELECT pg_get_functiondef('public.hg_delivery_pass(uuid,text,uuid,jsonb)'::regprocedure) INTO body;
 IF strpos(body,needle)=0 THEN RAISE EXCEPTION 'Delivery pass scan changed';END IF;
 EXECUTE replace(body,needle,replacement);
END$fairness$;
