-- Explicit owner previews only. No automatic staff enrolment or preference override.
CREATE TABLE hg_internal.engagement_campaign_observers (
 campaign_id uuid NOT NULL REFERENCES hg_internal.engagement_campaigns(id),
 user_id uuid NOT NULL REFERENCES public.profiles(id),
 added_by uuid NOT NULL REFERENCES public.profiles(id),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(campaign_id,user_id)
);
ALTER TABLE hg_internal.engagement_campaign_observers ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.engagement_campaign_observers FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,DELETE ON hg_internal.engagement_campaign_observers TO service_role;

CREATE FUNCTION public.hg_engagement_cycle_owner(p_campaign uuid,p_user uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM hg_internal.engagement_campaign_observers o
 JOIN hg_internal.engagement_campaigns c ON c.id=o.campaign_id JOIN profiles p ON p.id=o.user_id JOIN profiles actor ON actor.id=o.added_by
 WHERE o.campaign_id=p_campaign AND o.user_id=p_user AND p.is_active AND actor.is_active
 AND p.role::text IN ('admin','super_admin') AND actor.role::text IN ('admin','super_admin')
 AND (p.role::text='super_admin' OR p.campus_id=c.campus_id)
 AND (actor.role::text='super_admin' OR actor.campus_id=c.campus_id))
$$;
REVOKE ALL ON FUNCTION public.hg_engagement_cycle_owner(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_engagement_cycle_owner(uuid,uuid) TO service_role;

-- Add the narrow observer branch to the existing student predicates. Guarded
-- source replacements preserve all other campus, preference, lease and TTL logic.
DO $patch$
DECLARE definition text; needle text;
BEGIN
 SELECT pg_get_functiondef('public.hg_engagement_campaign_recipients(uuid,text,uuid)'::regprocedure) INTO definition;
 needle:='JOIN hg_internal.engagement_campaigns c ON c.campus_id=p.campus_id';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Recipient join changed; review observer patch'; END IF;
 definition:=replace(definition,needle,'JOIN hg_internal.engagement_campaigns c ON c.id=p_campaign');
 needle:='p.role::text=''student''';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Recipient role changed'; END IF;
 definition:=replace(definition,needle,'((p.role::text=''student'' AND p.campus_id=c.campus_id) OR public.hg_engagement_cycle_owner(c.id,p.id))');
 EXECUTE definition;
 SELECT pg_get_functiondef('public.hg_enqueue_engagement_campaign(uuid,integer,text,jsonb,timestamptz)'::regprocedure) INTO definition;
 needle:='p.campus_id=c.campus_id AND p.role::text=''student''';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Enqueue scope changed'; END IF;
 definition:=replace(definition,needle,'((p.campus_id=c.campus_id AND p.role::text=''student'') OR public.hg_engagement_cycle_owner(c.id,p.id))');
 needle:='''campaign_id'',c.id,''campaign_revision''';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Campaign metadata changed'; END IF;
 definition:=replace(definition,needle,'''campaign_campus_id'',c.campus_id,''campaign_id'',c.id,''campaign_revision''');
 EXECUTE definition;
 SELECT pg_get_functiondef('public.hg_engagement_campaign_notice_valid(uuid,integer,uuid)'::regprocedure) INTO definition;
 needle:='JOIN profiles p ON p.campus_id=c.campus_id';
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Notice join changed'; END IF;
 definition:=replace(definition,needle,'JOIN profiles p ON p.id=p_user');
 definition:=replace(definition,'p.role::text=''student''','((p.role::text=''student'' AND p.campus_id=c.campus_id) OR public.hg_engagement_cycle_owner(c.id,p.id))');
 EXECUTE definition;
END $patch$;
