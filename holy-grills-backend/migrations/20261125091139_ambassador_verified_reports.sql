-- Set-based verified metrics: one public API read replaces per-ambassador scans.
CREATE OR REPLACE FUNCTION public.hg_ambassador_insights(p_actor uuid,p_scope uuid,p_month text,p_week date,p_only uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; v_scope uuid:=p_scope; v_only uuid:=p_only; v_month_start timestamptz; v_month_end timestamptz; v_week_start timestamptz; v_week_end timestamptz; result jsonb;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 IF actor.role::text IN ('admin','community_manager') THEN
  IF actor.campus_id IS NULL OR (p_scope IS NOT NULL AND p_scope<>actor.campus_id) THEN RETURN jsonb_build_object('error','forbidden'); END IF; v_scope:=actor.campus_id;
 ELSIF actor.role::text<>'super_admin' THEN
  IF NOT EXISTS(SELECT 1 FROM ambassadors WHERE profile_id=p_actor AND status='active') OR (p_only IS NOT NULL AND p_only<>p_actor) OR (p_scope IS NOT NULL AND p_scope IS DISTINCT FROM actor.campus_id) THEN RETURN jsonb_build_object('error','forbidden'); END IF;
  v_scope:=actor.campus_id;v_only:=p_actor;
 END IF;
 IF p_month IS NULL OR p_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' OR p_week IS NULL OR extract(isodow FROM p_week)<>1 THEN RETURN jsonb_build_object('error','range'); END IF;
 v_month_start:=(p_month||'-01')::timestamp AT TIME ZONE 'Africa/Lagos';
 v_month_end:=((p_month||'-01')::date+interval '1 month')::timestamp AT TIME ZONE 'Africa/Lagos';
 v_week_start:=p_week::timestamp AT TIME ZONE 'Africa/Lagos';v_week_end:=(p_week+7)::timestamp AT TIME ZONE 'Africa/Lagos';
 WITH active AS MATERIALIZED (
  SELECT a.*,p.full_name,p.nickname,p.phone,p.referral_code,
   coalesce((SELECT (value#>>'{}')::integer FROM system_settings z WHERE z.key='ambassador_expected_weekly_shares' AND (z.campus_id=a.campus_id OR z.campus_id IS NULL) AND (value#>>'{}') ~ '^[1-9][0-9]{0,2}$' ORDER BY (z.campus_id IS NOT NULL) DESC LIMIT 1),4)
    * greatest(1,round(extract(day FROM ((p_month||'-01')::date+interval '1 month'-interval '1 day'))/7.0)::integer) AS monthly_target
   FROM ambassadors a JOIN profiles p ON p.id=a.profile_id
   WHERE a.status='active' AND p.is_active AND p.role::text<>'super_admin' AND a.campus_id IS NOT DISTINCT FROM p.campus_id
    AND (v_scope IS NULL OR a.campus_id=v_scope) AND (v_only IS NULL OR a.profile_id=v_only)
 ), relevant_visitors AS MATERIALIZED (
  SELECT DISTINCT visitor_user_id FROM ambassador_link_clicks WHERE visitor_user_id IS NOT NULL AND ambassador_id IN (SELECT profile_id FROM active)
 ), first_signup_click AS MATERIALIZED (
  SELECT DISTINCT ON(p.id) p.id AS user_id,c.ambassador_id,p.created_at FROM reporting_profiles p
   JOIN relevant_visitors rv ON rv.visitor_user_id=p.id JOIN ambassador_link_clicks c ON c.visitor_user_id=p.id JOIN ambassadors click_owner ON click_owner.profile_id=c.ambassador_id AND click_owner.campus_id IS NOT DISTINCT FROM p.campus_id
   WHERE c.ambassador_id<>p.id AND c.created_at<=p.created_at AND c.created_at>=p.created_at-make_interval(days=>hg_ambassador_window_days())
   ORDER BY p.id,c.created_at,c.id
 ), valid_orders AS MATERIALIZED (
  SELECT a.ambassador_id,o.delivered_at, greatest(0,o.total_amount-coalesce(o.card_refund_total,0)-coalesce(o.wallet_refund_total,0)) AS retained
   FROM ambassador_order_attributions a JOIN reporting_orders o ON o.id=a.order_id JOIN active p ON p.profile_id=a.ambassador_id
   WHERE a.eligibility='eligible' AND o.status::text='delivered' AND o.payment_status::text IN ('paid','partially_refunded')
    AND a.customer_user_id=o.user_id AND a.ambassador_id<>o.user_id AND a.campus_id IS NOT DISTINCT FROM o.campus_id
    AND o.campus_id IS NOT DISTINCT FROM p.campus_id
    AND (o.total_amount=0 OR o.total_amount>coalesce(o.card_refund_total,0)+coalesce(o.wallet_refund_total,0))
 ), signup_counts AS (
  SELECT ambassador_id,count(*) AS lifetime,count(*) FILTER(WHERE created_at>=v_month_start AND created_at<v_month_end) AS monthly,count(*) FILTER(WHERE created_at>=v_week_start AND created_at<v_week_end) AS weekly
   FROM first_signup_click GROUP BY ambassador_id
 ), order_counts AS (
  SELECT ambassador_id,count(*) AS lifetime,coalesce(sum(retained),0) AS retained,
   count(*) FILTER(WHERE delivered_at>=v_month_start AND delivered_at<v_month_end) AS monthly,
   count(*) FILTER(WHERE delivered_at>=v_week_start AND delivered_at<v_week_end) AS weekly,
   coalesce(sum(retained) FILTER(WHERE delivered_at>=v_week_start AND delivered_at<v_week_end),0) AS weekly_retained
   FROM valid_orders GROUP BY ambassador_id
 ), assignment_counts AS (
  SELECT a.ambassador_id,
   count(*) FILTER(WHERE a.month=p_month) AS assigned,
   count(*) FILTER(WHERE a.month=p_month AND a.status IN ('seen','shared')) AS seen,
   count(*) FILTER(WHERE a.month=p_month AND a.status='shared') AS shared,
   count(*) FILTER(WHERE a.created_at>=v_week_start AND a.created_at<v_week_end) AS week_assigned,
   count(*) FILTER(WHERE a.created_at>=v_week_start AND a.created_at<v_week_end AND a.status='shared') AS week_shared
   FROM ambassador_promo_assignments a JOIN ambassador_promo_messages m ON m.id=a.message_id
   WHERE m.deleted_at IS NULL GROUP BY a.ambassador_id
 )
 SELECT jsonb_build_object('month',p_month,'week_start',p_week,'week_end',p_week+6,'as_of',now(),
  'order_basis','Delivered and paid orders, net of completed refunds; test/super-admin orders excluded. Periods use delivery time in Lagos.',
  'share_basis','Manual confirmed shares of assignments created during the week; opening WhatsApp is not proof of sharing.',
  'ambassadors',coalesce(jsonb_agg(jsonb_build_object(
   'ambassador',jsonb_build_object('profile_id',a.profile_id,'campus_id',a.campus_id,'status',a.status,'whatsapp_phone',a.whatsapp_phone),
   'profile',jsonb_build_object('id',a.profile_id,'full_name',a.full_name,'nickname',a.nickname,'phone',a.phone,'referral_code',a.referral_code,'campus_id',a.campus_id),
   'lifetime',jsonb_build_object('total_signups',coalesce(s.lifetime,0),'total_orders',coalesce(o.lifetime,0),'total_order_value',coalesce(o.retained,0)),
   'month',jsonb_build_object('signups',coalesce(s.monthly,0),'orders',coalesce(o.monthly,0),'assigned_count',coalesce(c.assigned,0),'seen_count',coalesce(c.seen,0),'shared_count',coalesce(c.shared,0),
    'completion_rate',CASE WHEN c.assigned>0 THEN round(100.0*c.shared/c.assigned,2) ELSE 0 END,'monthly_share_target',a.monthly_target,'share_target_progress',least(100,round(100.0*coalesce(c.shared,0)/a.monthly_target,2))),
   'week',jsonb_build_object('signups',coalesce(s.weekly,0),'orders',coalesce(o.weekly,0),'retained_order_value',coalesce(o.weekly_retained,0),'assigned_count',coalesce(c.week_assigned,0),'shared_count',coalesce(c.week_shared,0))
  ) ORDER BY coalesce(a.nickname,a.full_name),a.profile_id),'[]'::jsonb)) INTO result
 FROM active a LEFT JOIN signup_counts s ON s.ambassador_id=a.profile_id LEFT JOIN order_counts o ON o.ambassador_id=a.profile_id LEFT JOIN assignment_counts c ON c.ambassador_id=a.profile_id;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_ambassador_insights(uuid,uuid,text,date,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_ambassador_insights(uuid,uuid,text,date,uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_hp_reconciliation(p_actor uuid,p_scope uuid,p_start timestamptz,p_end timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE; scope uuid:=p_scope; result jsonb;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 IF actor.role::text<>'super_admin' THEN
  IF actor.campus_id IS NULL OR (scope IS NOT NULL AND scope<>actor.campus_id) THEN RETURN jsonb_build_object('error','forbidden'); END IF; scope:=actor.campus_id;
 END IF;
 IF p_start IS NULL OR p_end IS NULL OR p_end<=p_start OR p_end-p_start>interval '366 days' THEN RETURN jsonb_build_object('error','range'); END IF;
 WITH owners AS MATERIALIZED(SELECT id,hp_balance FROM reporting_profiles WHERE scope IS NULL OR campus_id=scope),
 tx AS MATERIALIZED(SELECT t.* FROM reporting_hp_transactions t JOIN owners p ON p.id=t.user_id),
 per_source AS (
  SELECT coalesce(nullif(source,''),'unknown') AS source,
   coalesce(sum(greatest(coalesce(remaining_amount,0),0)) FILTER(WHERE type='earn' AND status='active'),0) AS active_remaining,
   coalesce(sum(amount) FILTER(WHERE type='earn' AND status='pending'),0) AS pending,
   coalesce(sum(amount) FILTER(WHERE type='earn' AND status='active' AND created_at>=p_start AND created_at<p_end),0) AS active_awarded_in_period,
   coalesce(sum(amount) FILTER(WHERE type='spend' AND status='active' AND created_at>=p_start AND created_at<p_end),0) AS spent_in_period,
   coalesce(sum(amount) FILTER(WHERE type='expire' AND created_at>=p_start AND created_at<p_end),0) AS expired_in_period,
   coalesce(sum(greatest(coalesce(remaining_amount,0),0)) FILTER(WHERE type='earn' AND status='active' AND expires_at<now()),0) AS expiry_due
  FROM tx GROUP BY coalesce(nullif(source,''),'unknown')
 )
 SELECT jsonb_build_object('as_of',now(),'period_start',p_start,'period_end',p_end,
  'scope_basis','Current account campus; super-admin accounts excluded. Balances are current stocks; award/spend totals are period flows.',
  'profile_active_balance',(SELECT coalesce(sum(hp_balance),0) FROM owners),
  'ledger_active_remaining',coalesce(sum(active_remaining),0),'pending_amount',coalesce(sum(pending),0),
  'active_balance_difference',(SELECT coalesce(sum(hp_balance),0) FROM owners)-coalesce(sum(active_remaining),0),
  'expiry_due',coalesce(sum(expiry_due),0),
  'sources',coalesce(jsonb_agg(to_jsonb(per_source) ORDER BY source),'[]'::jsonb)) INTO result FROM per_source;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_hp_reconciliation(uuid,uuid,timestamptz,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_hp_reconciliation(uuid,uuid,timestamptz,timestamptz) TO service_role;
