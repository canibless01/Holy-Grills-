-- Stage 4: scoped reporting only; current balance and dated changes are distinct.
CREATE FUNCTION public.hg_delivery_pool_report(p_actor uuid,p_campus uuid,p_from date,p_to date,p_export boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;result jsonb;rows jsonb;
BEGIN
 PERFORM hg_internal.delivery_cost_actor(p_actor,p_campus);
 IF p_from IS NULL OR p_to IS NULL OR p_from>p_to OR p_to-p_from>366 OR p_to>today THEN RAISE EXCEPTION 'Choose a date range of up to 367 days ending today or earlier' USING ERRCODE='22023';END IF;
 IF p_export THEN
  IF (SELECT count(*) FROM hg_internal.delivery_subsidy_ledger l WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded' AND l.delivery_date BETWEEN p_from AND p_to)>10000 THEN RAISE EXCEPTION 'Export is too large; choose a shorter range or one campus' USING ERRCODE='22023';END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.delivery_date,q.order_id),'[]'::jsonb) INTO rows FROM (
   SELECT l.order_id,c.name campus,g.name gate,l.delivery_date,l.status,l.payment_status,l.paid_total_original order_total,
    l.delivery_fee_original customer_delivery_fee,l.cushion_original cushion_snapshot,l.cushion_total recognized_cushion,
    l.delivery_fee_collected recognized_delivery_fee,l.rider_cost,l.rider_cost_date,l.net_effect
   FROM hg_internal.delivery_subsidy_ledger l JOIN public.campuses c ON c.id=l.campus_id LEFT JOIN public.gates g ON g.id=l.gate_id
   WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded' AND l.delivery_date BETWEEN p_from AND p_to
  )q;
  RETURN jsonb_build_object('rows',rows);
 END IF;
 SELECT jsonb_build_object(
  'balance',coalesce(sum(l.net_effect),0),
  'cushion_collected',coalesce(sum(l.cushion_total),0),
  'delivery_fees_collected',coalesce(sum(l.delivery_fee_collected),0),
  'rider_costs_recorded',coalesce(sum(l.rider_cost),0),
  'unrecorded_orders',count(*) FILTER(WHERE l.rider_cost IS NULL AND l.status IN ('delivered','delivery_attempted','unclaimed')),
  'unreconciled_collections',coalesce(sum(l.cushion_total+l.delivery_fee_collected) FILTER(WHERE l.rider_cost IS NULL),0)
 ) INTO result FROM hg_internal.delivery_subsidy_ledger l WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded';
 result:=result||jsonb_build_object('changes',(
  SELECT jsonb_build_object('today',coalesce(sum(delta) FILTER(WHERE (occurred_at AT TIME ZONE 'Africa/Lagos')::date=today),0),
   'week',coalesce(sum(delta) FILTER(WHERE (occurred_at AT TIME ZONE 'Africa/Lagos')::date>=date_trunc('week',today::timestamp)::date),0),
   'month',coalesce(sum(delta) FILTER(WHERE (occurred_at AT TIME ZONE 'Africa/Lagos')::date>=date_trunc('month',today::timestamp)::date),0))
  FROM hg_internal.delivery_subsidy_movements WHERE (p_campus IS NULL OR campus_id=p_campus)
 ));
 SELECT coalesce(jsonb_agg(to_jsonb(q) ORDER BY q.campus,q.gate),'[]'::jsonb) INTO rows FROM (
  SELECT l.campus_id,c.name campus,l.gate_id,coalesce(g.name,'Unassigned gate') gate,
   coalesce(sum(l.net_effect),0) balance,coalesce(sum(l.cushion_total),0) cushion,coalesce(sum(l.delivery_fee_collected),0) delivery_fees,coalesce(sum(l.rider_cost),0) rider_costs,
   count(*) FILTER(WHERE l.rider_cost IS NULL AND l.status IN ('delivered','delivery_attempted','unclaimed')) unrecorded
  FROM hg_internal.delivery_subsidy_ledger l JOIN public.campuses c ON c.id=l.campus_id LEFT JOIN public.gates g ON g.id=l.gate_id
  WHERE (p_campus IS NULL OR l.campus_id=p_campus) AND l.status<>'excluded' GROUP BY l.campus_id,c.name,l.gate_id,g.name
 )q;
 result:=result||jsonb_build_object('gates',rows);
 WITH opening AS (SELECT coalesce(sum(delta),0) amount FROM hg_internal.delivery_subsidy_movements WHERE (p_campus IS NULL OR campus_id=p_campus) AND occurred_at<(p_from::timestamp AT TIME ZONE 'Africa/Lagos')),
 days AS (SELECT generate_series(p_from::timestamp,p_to::timestamp,interval '1 day')::date AS day),
 changes AS (SELECT (occurred_at AT TIME ZONE 'Africa/Lagos')::date AS day,sum(delta) amount FROM hg_internal.delivery_subsidy_movements WHERE (p_campus IS NULL OR campus_id=p_campus) AND occurred_at>=(p_from::timestamp AT TIME ZONE 'Africa/Lagos') AND occurred_at<((p_to+1)::timestamp AT TIME ZONE 'Africa/Lagos') GROUP BY 1),
 points AS (SELECT d.day,coalesce(c.amount,0) change,(SELECT amount FROM opening)+sum(coalesce(c.amount,0)) OVER(ORDER BY d.day) balance FROM days d LEFT JOIN changes c USING(day))
 SELECT jsonb_agg(to_jsonb(points) ORDER BY day) INTO rows FROM points;
 RETURN result||jsonb_build_object('trend',rows,'as_of',now(),'from_date',p_from,'to_date',p_to);
END$$;
REVOKE ALL ON FUNCTION public.hg_delivery_pool_report(uuid,uuid,date,date,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_delivery_pool_report(uuid,uuid,date,date,boolean) TO service_role;
