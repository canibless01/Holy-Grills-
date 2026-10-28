-- Replace one admission predicate in the existing signature; no new overload.
DO $migration$
DECLARE body text; original text; replacement text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO body FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='hg_create_order_atomic' AND p.pronargs=38;
 original:='SELECT capacity INTO v_capacity FROM ordering_windows
          WHERE id=p_ordering_window_id AND campus_id=p_campus_id AND NOT is_closed;';
 replacement:='SELECT ow.capacity INTO v_capacity FROM public.ordering_windows ow
          WHERE ow.id=p_ordering_window_id AND ow.campus_id=p_campus_id
          AND CASE
            WHEN ow.date IS NOT NULL THEN ow.date=v_target_date AND NOT ow.is_closed
            WHEN EXISTS(SELECT 1 FROM public.ordering_windows dated WHERE dated.campus_id=p_campus_id AND dated.date=v_target_date) THEN false
            WHEN EXISTS(SELECT 1 FROM public.operating_hour_overrides h WHERE h.date=v_target_date AND (h.campus_id=p_campus_id OR h.campus_id IS NULL)) THEN
              ow.weekday=extract(isodow FROM v_target_date)::integer-1
              AND (SELECT count(*) FROM public.ordering_windows weekly WHERE weekly.campus_id=p_campus_id AND weekly.date IS NULL AND weekly.weekday=ow.weekday)=1
              AND NOT (SELECT h.is_closed FROM public.operating_hour_overrides h WHERE h.date=v_target_date AND (h.campus_id=p_campus_id OR h.campus_id IS NULL) ORDER BY (h.campus_id IS NOT NULL) DESC LIMIT 1)
            ELSE ow.weekday=extract(isodow FROM v_target_date)::integer-1 AND NOT ow.is_closed
          END;';
 IF body IS NULL OR position(original IN body)=0 THEN RAISE EXCEPTION 'order_admission_definition_changed'; END IF;
 EXECUTE replace(body,original,replacement);
END $migration$;
