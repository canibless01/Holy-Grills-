-- Offset from event start naturally follows an approved reschedule. NULL keeps
-- existing unrestricted opening behavior. Admission always stops at event end.
CREATE OR REPLACE FUNCTION public.hg_set_event_admission_window(p_actor uuid,p_event uuid,p_minutes integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;e public.events%rowtype;previous jsonb;next_value jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO e FROM public.events WHERE id=p_event FOR UPDATE;
 IF NOT FOUND OR (a.role::text<>'super_admin' AND (e.campus_id IS NULL OR a.campus_id IS DISTINCT FROM e.campus_id)) THEN RAISE EXCEPTION 'HG_ORGANIZER_ACCESS' USING ERRCODE='42501';END IF;
 IF p_minutes IS NOT NULL AND (p_minutes<0 OR p_minutes>10080) THEN RAISE EXCEPTION 'HG_ADMISSION_WINDOW_INVALID';END IF;
 previous:=e.metadata->'checkin_minutes_before_start';next_value:=coalesce(to_jsonb(p_minutes),'null'::jsonb);
 IF coalesce(previous,'null'::jsonb)=next_value THEN RETURN jsonb_build_object('minutes',p_minutes,'replayed',true);END IF;
 IF e.metadata->>'lifecycle_status'='cancelled' OR e.ends_at<=now() OR EXISTS(SELECT 1 FROM public.event_checkins ci JOIN public.event_tickets t ON t.id=ci.ticket_id WHERE t.event_id=e.id) THEN RAISE EXCEPTION 'HG_ADMISSION_WINDOW_LOCKED';END IF;
 UPDATE public.events SET metadata=coalesce(metadata,'{}')||jsonb_build_object('checkin_minutes_before_start',p_minutes) WHERE id=e.id;
 INSERT INTO public.admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value) VALUES(a.id,a.role::text,'event',e.id::text,'admission_window_changed',jsonb_build_object('minutes',previous),jsonb_build_object('minutes',p_minutes));
 RETURN jsonb_build_object('minutes',p_minutes,'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.hg_set_event_admission_window(uuid,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_set_event_admission_window(uuid,uuid,integer) TO service_role;
DO $$ DECLARE definition text;needle text:=' IF NOT recovering THEN';BEGIN
 definition:=pg_get_functiondef('public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer)'::regprocedure);
 IF md5(definition)<>'168371cbdfe7fe7c45e9469f0b6f2704' OR position(needle IN definition)=0 THEN RAISE EXCEPTION 'Admission source changed';END IF;
 definition:=replace(definition,needle,$patch$
 IF NOT recovering AND e.metadata->>'checkin_minutes_before_start' IS NOT NULL THEN
  IF coalesce(e.metadata->>'checkin_minutes_before_start','') !~ '^\d{1,5}$' OR (e.metadata->>'checkin_minutes_before_start')::integer>10080 THEN RAISE EXCEPTION 'HG_ADMISSION_WINDOW_INVALID';END IF;
  IF now()<e.starts_at-make_interval(mins=>(e.metadata->>'checkin_minutes_before_start')::integer) THEN RAISE EXCEPTION 'HG_ADMISSION_NOT_OPEN';END IF;
 END IF;
 IF NOT recovering THEN$patch$);
 EXECUTE definition;
END $$;
REVOKE ALL ON FUNCTION public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_admit_event_ticket(uuid,uuid,uuid,text,uuid,integer) TO service_role;
