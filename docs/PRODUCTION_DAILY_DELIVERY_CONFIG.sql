-- Authorized production configuration: 19:30–20:30 Africa/Lagos every day.
-- No schema changes, historical deletions or customer/reward modifications.
-- Reuses existing matching weekly rows and updates existing ordering links.
BEGIN;
DO $config$
DECLARE c record; weekday_no integer; delivery_id uuid; existing_count integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended('production-daily-delivery-1930-2030',0));
  IF (SELECT count(*) FROM public.campuses WHERE id IN
      ('70000001-cafe-cafe-cafe-000000000001'::uuid,'70000002-cafe-cafe-cafe-000000000002'::uuid)
      AND is_active AND lower(name) NOT LIKE '%audit%') <> 2 THEN
    RAISE EXCEPTION 'Expected active FUTA and Lagos campuses; review configuration scope';
  END IF;
  FOR c IN SELECT id FROM public.campuses WHERE id IN
      ('70000001-cafe-cafe-cafe-000000000001'::uuid,'70000002-cafe-cafe-cafe-000000000002'::uuid)
  LOOP
    IF EXISTS (SELECT 1 FROM public.delivery_windows WHERE campus_id=c.id
       AND weekday IS NOT NULL AND date IS NULL AND is_active AND NOT is_closed
       AND status NOT IN ('cancelled','closed')
       AND (opens_at IS DISTINCT FROM '19:30'::time OR closes_at IS DISTINCT FROM '20:30'::time)) THEN
      RAISE EXCEPTION 'Another active recurring delivery schedule exists; review before replacing it';
    END IF;
    FOR weekday_no IN 0..6 LOOP
      SELECT count(*), (array_agg(id ORDER BY created_at,id))[1] INTO existing_count,delivery_id
        FROM public.delivery_windows WHERE campus_id=c.id AND weekday=weekday_no AND date IS NULL
        AND opens_at='19:30'::time AND closes_at='20:30'::time;
      IF existing_count>1 THEN RAISE EXCEPTION 'Duplicate configured delivery slots require review'; END IF;
      IF existing_count=0 THEN
        INSERT INTO public.delivery_windows(campus_id,weekday,label,opens_at,closes_at,status,is_active,is_closed)
        VALUES(c.id,weekday_no,'Daily delivery · 7:30–8:30 PM','19:30','20:30','open',true,false)
        RETURNING id INTO delivery_id;
      ELSE
        UPDATE public.delivery_windows SET status='open',is_active=true,is_closed=false
          WHERE id=delivery_id;
      END IF;
      UPDATE public.ordering_windows SET linked_delivery_window_id=delivery_id,updated_at=now()
        WHERE campus_id=c.id AND weekday=weekday_no AND date IS NULL
          AND linked_delivery_window_id IS DISTINCT FROM delivery_id;
    END LOOP;
  END LOOP;
END;
$config$;
SELECT campus_id,count(*) slots,min(opens_at) starts,max(closes_at) ends
FROM public.delivery_windows WHERE campus_id IN
 ('70000001-cafe-cafe-cafe-000000000001'::uuid,'70000002-cafe-cafe-cafe-000000000002'::uuid)
 AND weekday IS NOT NULL AND date IS NULL AND is_active AND NOT is_closed AND status='open'
GROUP BY campus_id;
COMMIT;
