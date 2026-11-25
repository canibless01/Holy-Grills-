-- First-party, opt-in page measurement. No IP, email, URL query or claim token is stored.
CREATE TABLE IF NOT EXISTS hg_internal.engagement_page_events(
 id uuid PRIMARY KEY, visitor_id uuid NOT NULL, user_id uuid REFERENCES public.profiles(id),
 campus_id uuid NOT NULL REFERENCES public.campuses(id), path text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now(),
 CHECK(path IN ('/','/menu','/menu/:item','/checkout','/register','/login','/dashboard','/rewards','/wallet','/profile','/orders','/orders/:order','/events','/events/:event','/marketplace','/marketplace/:item','/referrals','/streak','/squads','/our-story','/faq','/contact'))
);
CREATE INDEX IF NOT EXISTS engagement_events_campus_time ON hg_internal.engagement_page_events(campus_id,occurred_at);
CREATE INDEX IF NOT EXISTS engagement_events_visitor_time ON hg_internal.engagement_page_events(visitor_id,occurred_at);
CREATE TABLE IF NOT EXISTS hg_internal.engagement_activity(
 user_id uuid NOT NULL REFERENCES public.profiles(id), campus_id uuid NOT NULL REFERENCES public.campuses(id),
 bucket timestamptz NOT NULL, seen_at timestamptz NOT NULL,
 PRIMARY KEY(user_id,campus_id,bucket)
);
CREATE INDEX IF NOT EXISTS engagement_activity_campus_time ON hg_internal.engagement_activity(campus_id,seen_at);
CREATE TABLE IF NOT EXISTS hg_internal.engagement_streak_weeks(
 user_id uuid NOT NULL REFERENCES public.profiles(id),campus_id uuid NOT NULL REFERENCES public.campuses(id),
 week_start date NOT NULL,receipt jsonb NOT NULL,recorded_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(user_id,week_start)
);
CREATE INDEX IF NOT EXISTS engagement_streak_campus_week ON hg_internal.engagement_streak_weeks(campus_id,week_start);
ALTER TABLE hg_internal.engagement_page_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.engagement_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE hg_internal.engagement_streak_weeks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.engagement_page_events,hg_internal.engagement_activity,hg_internal.engagement_streak_weeks FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA hg_internal TO service_role;
GRANT SELECT,INSERT,UPDATE ON hg_internal.engagement_page_events,hg_internal.engagement_activity,hg_internal.engagement_streak_weeks TO service_role;

-- Private audit trigger: authenticated profile updates must not need write access to analytics tables.
CREATE OR REPLACE FUNCTION hg_internal.capture_engagement_activity() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.is_active AND NEW.role::text='student' AND NEW.campus_id IS NOT NULL AND NEW.last_seen_at IS NOT NULL THEN
  INSERT INTO hg_internal.engagement_activity(user_id,campus_id,bucket,seen_at)
   VALUES(NEW.id,NEW.campus_id,date_bin('30 minutes',NEW.last_seen_at,'2000-01-01'::timestamptz),NEW.last_seen_at) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.capture_engagement_activity() FROM PUBLIC,anon,authenticated;
CREATE OR REPLACE TRIGGER hg_engagement_activity_capture AFTER INSERT OR UPDATE OF last_seen_at ON public.profiles
 FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_engagement_activity();

CREATE OR REPLACE FUNCTION hg_internal.capture_engagement_streak_week() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE campus uuid;start_day date;
BEGIN
 IF jsonb_typeof(NEW.last_week_receipt)<>'object' OR coalesce(NEW.last_week_receipt->>'week_start','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RETURN NEW; END IF;
 BEGIN start_day:=(NEW.last_week_receipt->>'week_start')::date;
 EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NEW; END;
 IF extract(isodow FROM start_day)<>1 THEN RETURN NEW; END IF;
 SELECT p.campus_id INTO campus FROM public.profiles p WHERE p.id=NEW.user_id AND p.role::text='student';
 IF campus IS NULL THEN RETURN NEW; END IF;
 INSERT INTO hg_internal.engagement_streak_weeks(user_id,campus_id,week_start,receipt)
 VALUES(NEW.user_id,campus,start_day,NEW.last_week_receipt)
 ON CONFLICT(user_id,week_start) DO UPDATE SET receipt=excluded.receipt,recorded_at=now();
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.capture_engagement_streak_week() FROM PUBLIC,anon,authenticated;
CREATE OR REPLACE TRIGGER hg_engagement_streak_capture AFTER INSERT OR UPDATE OF last_week_receipt ON public.login_streaks
 FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_engagement_streak_week();

-- Seed only the latest real settlement receipt each account already has.
DO $$
DECLARE r record; settled date;
BEGIN
 FOR r IN SELECT s.user_id,p.campus_id,s.last_week_receipt receipt FROM public.login_streaks s JOIN public.profiles p ON p.id=s.user_id
   WHERE p.role::text='student' AND p.campus_id IS NOT NULL AND jsonb_typeof(s.last_week_receipt)='object' LOOP
  BEGIN settled:=(r.receipt->>'week_start')::date;
  EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN CONTINUE; END;
  IF settled IS NOT NULL AND extract(isodow FROM settled)=1 THEN
   INSERT INTO hg_internal.engagement_streak_weeks(user_id,campus_id,week_start,receipt)
   VALUES(r.user_id,r.campus_id,settled,r.receipt) ON CONFLICT DO NOTHING;
  END IF;
 END LOOP;
END $$;

-- Reuse only actual last-seen observations; never invent historical visits.
INSERT INTO hg_internal.engagement_activity(user_id,campus_id,bucket,seen_at)
 SELECT id,campus_id,date_bin('30 minutes',last_seen_at,'2000-01-01'::timestamptz),last_seen_at FROM public.profiles
 WHERE role::text='student' AND is_active AND campus_id IS NOT NULL AND last_seen_at IS NOT NULL ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION public.hg_record_engagement_page(p_id uuid,p_visitor uuid,p_user uuid,p_campus uuid,p_path text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE;
BEGIN
 IF p_id IS NULL OR p_visitor IS NULL OR p_campus IS NULL OR NOT EXISTS(SELECT 1 FROM campuses WHERE id=p_campus AND is_active) THEN RETURN jsonb_build_object('error','invalid'); END IF;
 IF p_user IS NOT NULL THEN
  SELECT * INTO actor FROM profiles WHERE id=p_user AND is_active;
  IF NOT FOUND OR actor.campus_id IS DISTINCT FROM p_campus THEN RETURN jsonb_build_object('error','forbidden'); END IF;
  IF actor.role::text<>'student' THEN RETURN jsonb_build_object('accepted',false,'ignored_staff',true); END IF;
 END IF;
 IF p_path IS NULL OR p_path NOT IN ('/','/menu','/menu/:item','/checkout','/register','/login','/dashboard','/rewards','/wallet','/profile','/orders','/orders/:order','/events','/events/:event','/marketplace','/marketplace/:item','/referrals','/streak','/squads','/our-story','/faq','/contact') THEN RETURN jsonb_build_object('error','invalid'); END IF;
 INSERT INTO hg_internal.engagement_page_events(id,visitor_id,user_id,campus_id,path) VALUES(p_id,p_visitor,p_user,p_campus,p_path) ON CONFLICT DO NOTHING;
 RETURN jsonb_build_object('accepted',true);
END $$;
REVOKE ALL ON FUNCTION public.hg_record_engagement_page(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_record_engagement_page(uuid,uuid,uuid,uuid,text) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_engagement_summary(p_campus uuid,p_start timestamptz,p_end timestamptz,p_include_hp boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE result jsonb; hp jsonb;streak jsonb;v_today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
BEGIN
 IF p_start IS NULL OR p_end IS NULL OR p_end<=p_start OR p_end-p_start>interval '366 days' THEN RETURN jsonb_build_object('error','range'); END IF;
 WITH activity AS MATERIALIZED(SELECT a.* FROM hg_internal.engagement_activity a JOIN profiles p ON p.id=a.user_id WHERE p.role::text='student' AND (p_campus IS NULL OR a.campus_id=p_campus)),
 events AS MATERIALIZED(SELECT e.* FROM hg_internal.engagement_page_events e LEFT JOIN profiles p ON p.id=e.user_id WHERE (e.user_id IS NULL OR p.role::text='student') AND (p_campus IS NULL OR e.campus_id=p_campus)),
 period_events AS MATERIALIZED(SELECT * FROM events WHERE occurred_at>=p_start AND occurred_at<p_end),
 visitors AS MATERIALIZED(SELECT visitor_id,min(occurred_at) first_seen,min(occurred_at) FILTER(WHERE path LIKE '/menu%') menu_at FROM period_events GROUP BY visitor_id),
 checkout AS MATERIALIZED(SELECT v.visitor_id,min(e.occurred_at) checkout_at FROM visitors v JOIN period_events e ON e.visitor_id=v.visitor_id AND e.path='/checkout' AND e.occurred_at>=v.menu_at GROUP BY v.visitor_id),
 identity AS MATERIALIZED(SELECT DISTINCT ON(visitor_id) visitor_id,user_id FROM period_events WHERE user_id IS NOT NULL ORDER BY visitor_id,occurred_at),
 paid_visitors AS (SELECT DISTINCT c.visitor_id FROM checkout c JOIN identity i ON i.visitor_id=c.visitor_id JOIN reporting_orders o ON o.user_id=i.user_id AND (p_campus IS NULL OR o.campus_id=p_campus)
  WHERE o.payment_status::text IN ('paid','partially_refunded') AND coalesce(o.paid_at,o.payment_confirmed_at)>=c.checkout_at AND coalesce(o.paid_at,o.payment_confirmed_at)<p_end),
 days AS(SELECT generate_series((p_start AT TIME ZONE 'Africa/Lagos')::date,((p_end-interval '1 microsecond') AT TIME ZONE 'Africa/Lagos')::date,'1 day')::date AS calendar_day)
 SELECT jsonb_build_object('as_of',now(),'period_start',p_start,'period_end',p_end,
  'tracking_started_at',(SELECT min(occurred_at) FROM events),
  'dau',(SELECT count(DISTINCT user_id) FROM activity WHERE (seen_at AT TIME ZONE 'Africa/Lagos')::date=v_today),
  'mau',(SELECT count(DISTINCT user_id) FROM activity WHERE seen_at>=now()-interval '30 days'),
  'active_users',(SELECT count(DISTINCT user_id) FROM activity WHERE seen_at>=p_start AND seen_at<p_end),
  'page_views',(SELECT count(*) FROM period_events),'visitors',(SELECT count(DISTINCT visitor_id) FROM period_events),
  'new_signups',(SELECT count(*) FROM reporting_profiles WHERE role::text='student' AND (p_campus IS NULL OR campus_id=p_campus) AND created_at>=p_start AND created_at<p_end),
  'daily_ordering_users',(SELECT count(DISTINCT user_id) FROM reporting_orders WHERE (p_campus IS NULL OR campus_id=p_campus) AND (created_at AT TIME ZONE 'Africa/Lagos')::date=v_today),
  'monthly_ordering_users',(SELECT count(DISTINCT user_id) FROM reporting_orders WHERE (p_campus IS NULL OR campus_id=p_campus) AND created_at>=now()-interval '30 days'),
  'total_active_users',(SELECT count(*) FROM reporting_profiles WHERE role::text='student' AND is_active AND (p_campus IS NULL OR campus_id=p_campus)),
  'tier_breakdown',(SELECT coalesce(jsonb_object_agg(tier,n),'{}'::jsonb) FROM (SELECT coalesce(t.name,'untiered') tier,count(*) n FROM reporting_profiles p LEFT JOIN hp_tiers t ON t.id=p.current_tier_id WHERE p.role::text='student' AND p.is_active AND (p_campus IS NULL OR p.campus_id=p_campus) GROUP BY coalesce(t.name,'untiered')) z),
  'funnel',jsonb_build_object('visitors',(SELECT count(*) FROM visitors),'menu_visitors',(SELECT count(*) FROM visitors WHERE menu_at IS NOT NULL),'checkout_after_menu',(SELECT count(*) FROM checkout),'paid_linked_accounts',(SELECT count(*) FROM paid_visitors)),
  'pages',(SELECT coalesce(jsonb_agg(to_jsonb(z) ORDER BY views DESC),'[]'::jsonb) FROM (SELECT path,count(*) views,count(DISTINCT visitor_id) visitors FROM period_events GROUP BY path) z),
  'daily',(SELECT coalesce(jsonb_agg(jsonb_build_object('day',calendar_day,
   'active_users',(SELECT count(DISTINCT user_id) FROM activity WHERE (seen_at AT TIME ZONE 'Africa/Lagos')::date=calendar_day AND seen_at>=p_start AND seen_at<p_end),
   'page_views',(SELECT count(*) FROM period_events WHERE (occurred_at AT TIME ZONE 'Africa/Lagos')::date=calendar_day),
   'visitors',(SELECT count(DISTINCT visitor_id) FROM period_events WHERE (occurred_at AT TIME ZONE 'Africa/Lagos')::date=calendar_day),
   'checkins',(SELECT count(*) FROM daily_checkins c JOIN reporting_profiles p ON p.id=c.user_id WHERE c.checkin_date=calendar_day AND p.role::text='student' AND (p_campus IS NULL OR p.campus_id=p_campus))) ORDER BY calendar_day),'[]'::jsonb) FROM days)
 ) INTO result;
 SELECT jsonb_build_object('qualified_weeks',count(*) FILTER(WHERE receipt->>'previous_week_completed'='true'),'failed_weeks',count(*) FILTER(WHERE receipt->>'previous_week_completed'='false'),
  'outcomes_tracked_from',min(recorded_at)) INTO streak FROM hg_internal.engagement_streak_weeks s JOIN reporting_profiles p ON p.id=s.user_id
  WHERE p.role::text='student' AND (p_campus IS NULL OR s.campus_id=p_campus) AND ((s.week_start+7)::timestamp AT TIME ZONE 'Africa/Lagos')>=p_start AND ((s.week_start+7)::timestamp AT TIME ZONE 'Africa/Lagos')<p_end;
 result:=result||jsonb_build_object('streaks',streak);
 IF p_include_hp THEN
  WITH owners AS(SELECT * FROM reporting_profiles WHERE p_campus IS NULL OR campus_id=p_campus),
  sources AS(SELECT coalesce(t.source,'unknown') source,
    coalesce(sum(coalesce(t.remaining_amount,0)) FILTER(WHERE t.type='earn' AND t.status='active'),0) active,
    coalesce(sum(t.amount) FILTER(WHERE t.type='earn' AND t.status='pending'),0) pending
    FROM reporting_hp_transactions t JOIN owners p ON p.id=t.user_id GROUP BY coalesce(t.source,'unknown'))
  SELECT jsonb_build_object('as_of',now(),'active',(SELECT coalesce(sum(hp_balance),0) FROM owners),'ledger',coalesce(sum(active),0),'pending',coalesce(sum(pending),0),
    'difference',(SELECT coalesce(sum(hp_balance),0) FROM owners)-coalesce(sum(active),0),'sources',coalesce(jsonb_agg(to_jsonb(sources) ORDER BY source),'[]'::jsonb)) INTO hp FROM sources;
  result:=result||jsonb_build_object('hp',hp);
 END IF;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.hg_engagement_summary(uuid,timestamptz,timestamptz,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_engagement_summary(uuid,timestamptz,timestamptz,boolean) TO service_role;

CREATE OR REPLACE FUNCTION public.hg_engagement_report(p_actor uuid,p_scope uuid,p_start timestamptz,p_end timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=public AS $$
DECLARE actor public.profiles%ROWTYPE;scope uuid:=p_scope;
BEGIN
 SELECT * INTO actor FROM profiles WHERE id=p_actor AND is_active;
 IF NOT FOUND OR actor.role::text NOT IN ('admin','super_admin') THEN RETURN jsonb_build_object('error','forbidden'); END IF;
 IF actor.role::text<>'super_admin' THEN
  IF actor.campus_id IS NULL OR (scope IS NOT NULL AND scope<>actor.campus_id) THEN RETURN jsonb_build_object('error','forbidden'); END IF;scope:=actor.campus_id;
 END IF;
 RETURN hg_engagement_summary(scope,p_start,p_end,false);
END $$;
REVOKE ALL ON FUNCTION public.hg_engagement_report(uuid,uuid,timestamptz,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_engagement_report(uuid,uuid,timestamptz,timestamptz) TO service_role;
