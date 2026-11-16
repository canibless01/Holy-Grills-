-- Stage 5: private per-campus in-app setting; no environment variable or cron.
CREATE TABLE hg_internal.delivery_pool_budgets (
 campus_id uuid PRIMARY KEY REFERENCES public.campuses(id),
 floor numeric(14,2) NOT NULL DEFAULT 0 CHECK(floor>=0 AND floor::text NOT IN ('NaN','Infinity','-Infinity')),
 version integer NOT NULL DEFAULT 1, updated_by uuid NOT NULL REFERENCES public.profiles(id),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX delivery_pool_budget_actor ON hg_internal.delivery_pool_budgets(updated_by);
ALTER TABLE hg_internal.delivery_pool_budgets ENABLE ROW LEVEL SECURITY;
CREATE POLICY delivery_pool_budget_service ON hg_internal.delivery_pool_budgets FOR ALL TO service_role USING(true) WITH CHECK(true);
REVOKE ALL ON hg_internal.delivery_pool_budgets FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.delivery_pool_budgets TO service_role;
CREATE FUNCTION public.hg_delivery_pool_budget(p_actor uuid,p_campus uuid,p_floor numeric DEFAULT NULL,p_version integer DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE result jsonb;current_version integer;
BEGIN
 PERFORM hg_internal.delivery_cost_actor(p_actor,p_campus);
 IF p_floor IS NOT NULL THEN
  IF p_campus IS NULL OR p_floor<0 OR p_floor>999999999999.99 OR p_floor<>round(p_floor,2) OR p_floor::text IN ('NaN','Infinity','-Infinity') OR p_version IS NULL THEN RAISE EXCEPTION 'Choose a campus and a valid non-negative floor' USING ERRCODE='22023';END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('delivery-pool-budget:'||p_campus::text,0));
  SELECT version INTO current_version FROM hg_internal.delivery_pool_budgets WHERE campus_id=p_campus FOR UPDATE;
  IF coalesce(current_version,0)<>p_version THEN
   -- A retry of an already applied value is harmless, but never overwrites a newer different value.
   IF NOT EXISTS(SELECT 1 FROM hg_internal.delivery_pool_budgets WHERE campus_id=p_campus AND floor=p_floor AND updated_by=p_actor AND version=p_version+1) THEN
    RAISE EXCEPTION 'Budget changed; reload before editing' USING ERRCODE='40001';
   END IF;
  ELSE
   INSERT INTO hg_internal.delivery_pool_budgets(campus_id,floor,updated_by) VALUES(p_campus,p_floor,p_actor)
   ON CONFLICT(campus_id) DO UPDATE SET floor=EXCLUDED.floor,version=delivery_pool_budgets.version+1,updated_by=p_actor,updated_at=now();
  END IF;
 END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.campus),'[]'::jsonb) INTO result FROM (
  SELECT c.id campus_id,c.name campus,coalesce(b.floor,0) floor,coalesce(b.version,0) version,
   coalesce((SELECT sum(l.net_effect) FROM hg_internal.delivery_subsidy_ledger l WHERE l.campus_id=c.id AND l.status<>'excluded'),0) balance
  FROM public.campuses c LEFT JOIN hg_internal.delivery_pool_budgets b ON b.campus_id=c.id
  WHERE (p_campus IS NULL OR c.id=p_campus) AND (c.is_active OR EXISTS(SELECT 1 FROM hg_internal.delivery_subsidy_ledger l WHERE l.campus_id=c.id))
 )q;
 RETURN result;
END$$;
REVOKE ALL ON FUNCTION public.hg_delivery_pool_budget(uuid,uuid,numeric,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_delivery_pool_budget(uuid,uuid,numeric,integer) TO service_role;
