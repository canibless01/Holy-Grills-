-- Multi-store configuration only. Existing checkout remains campus-scoped until
-- the later fulfilment cutover migration removes the activation guard.
CREATE TABLE public.universities(
 id uuid PRIMARY KEY, name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 160),
 slug text NOT NULL UNIQUE CHECK(slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),is_active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.universities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.universities FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.universities TO service_role;
ALTER TABLE public.campuses ADD COLUMN university_id uuid REFERENCES public.universities(id);
CREATE INDEX campuses_university ON public.campuses(university_id) WHERE university_id IS NOT NULL;
CREATE TABLE public.stores(
 id uuid PRIMARY KEY, campus_id uuid NOT NULL REFERENCES public.campuses(id),
 name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 120),
 slug text NOT NULL CHECK(slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
 address text NOT NULL CHECK(length(btrim(address)) BETWEEN 1 AND 500),instructions text NOT NULL DEFAULT '' CHECK(length(instructions)<=500),
 lat double precision,lon double precision,is_active boolean NOT NULL DEFAULT true,
 pickup_enabled boolean NOT NULL DEFAULT true,delivery_enabled boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(campus_id,slug),UNIQUE(campus_id,id),
 CHECK((lat IS NULL AND lon IS NULL) OR (lat IS NOT NULL AND lon IS NOT NULL AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180)),
 CHECK(NOT is_active OR pickup_enabled OR delivery_enabled)
);
ALTER TABLE public.stores ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.stores FROM PUBLIC,anon,authenticated;
GRANT ALL ON public.stores TO service_role;
CREATE INDEX stores_campus_active ON public.stores(campus_id,is_active);
CREATE TABLE hg_internal.store_staff(
 store_id uuid NOT NULL REFERENCES public.stores(id),user_id uuid NOT NULL REFERENCES public.profiles(id),
 assigned_by uuid NOT NULL REFERENCES public.profiles(id),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(store_id,user_id)
);
ALTER TABLE hg_internal.store_staff ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.store_staff FROM PUBLIC,anon,authenticated;
GRANT ALL ON hg_internal.store_staff TO service_role;
CREATE INDEX store_staff_user ON hg_internal.store_staff(user_id,store_id);

CREATE FUNCTION hg_internal.may_manage_store_scope(p_actor uuid,p_campus uuid) RETURNS boolean
LANGUAGE sql SECURITY INVOKER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_actor AND is_active AND
 (role::text='super_admin' OR (role::text='admin' AND campus_id=p_campus)));
$$;
REVOKE ALL ON FUNCTION hg_internal.may_manage_store_scope(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.may_manage_store_scope(uuid,uuid) TO service_role;

CREATE FUNCTION public.hg_save_university(p_actor uuid,p_id uuid,p_data jsonb,p_expected timestamptz DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE u public.universities;before_row jsonb;actor_role text;
BEGIN
 SELECT role::text INTO actor_role FROM profiles WHERE id=p_actor AND is_active FOR SHARE;
 IF actor_role IS DISTINCT FROM 'super_admin' THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('university:'||p_id,0));
 SELECT * INTO u FROM universities WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
  IF p_expected IS NULL THEN
   IF u.name=p_data->>'name' AND u.slug=p_data->>'slug' AND u.is_active=(p_data->>'is_active')::boolean THEN RETURN to_jsonb(u);END IF;
   RAISE EXCEPTION 'HG_STORE_CONFLICT';
  END IF;
  IF u.updated_at<>p_expected THEN RAISE EXCEPTION 'HG_STORE_CONFLICT';END IF;
  before_row:=to_jsonb(u);
  UPDATE universities SET name=p_data->>'name',slug=p_data->>'slug',is_active=(p_data->>'is_active')::boolean,updated_at=clock_timestamp() WHERE id=p_id RETURNING * INTO u;
 ELSE
  IF p_expected IS NOT NULL THEN RAISE EXCEPTION 'HG_STORE_NOT_FOUND';END IF;
  INSERT INTO universities(id,name,slug,is_active) VALUES(p_id,p_data->>'name',p_data->>'slug',(p_data->>'is_active')::boolean) RETURNING * INTO u;
 END IF;
 INSERT INTO admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value)
 VALUES(p_actor,actor_role,'universities',p_id::text,'save_university',before_row,to_jsonb(u));
 RETURN to_jsonb(u);
END $$;
REVOKE ALL ON FUNCTION public.hg_save_university(uuid,uuid,jsonb,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_save_university(uuid,uuid,jsonb,timestamptz) TO service_role;

CREATE FUNCTION public.hg_link_university_campus(p_actor uuid,p_campus uuid,p_university uuid,p_expected timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c public.campuses;before_row jsonb;
BEGIN
 PERFORM 1 FROM profiles WHERE id=p_actor AND is_active AND role::text='super_admin' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO c FROM campuses WHERE id=p_campus FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_STORE_NOT_FOUND';END IF;
 IF c.updated_at IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'HG_STORE_CONFLICT';END IF;
 IF p_university IS NOT NULL THEN
  PERFORM 1 FROM universities WHERE id=p_university AND is_active FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'HG_STORE_UNIVERSITY_UNAVAILABLE';END IF;
 END IF;
 before_row:=to_jsonb(c);
 UPDATE campuses SET university_id=p_university,updated_at=clock_timestamp() WHERE id=p_campus RETURNING * INTO c;
 INSERT INTO admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value,campus_id)
 VALUES(p_actor,'super_admin','campuses',p_campus::text,'link_campus_university',before_row,to_jsonb(c),p_campus);
 RETURN to_jsonb(c);
END $$;
REVOKE ALL ON FUNCTION public.hg_link_university_campus(uuid,uuid,uuid,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_link_university_campus(uuid,uuid,uuid,timestamptz) TO service_role;

CREATE FUNCTION public.hg_save_store(p_actor uuid,p_id uuid,p_campus uuid,p_data jsonb,p_expected timestamptz DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.stores;before_row jsonb;actor_role text;
BEGIN
 IF NOT hg_internal.may_manage_store_scope(p_actor,p_campus) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 PERFORM 1 FROM public.campuses WHERE id=p_campus AND is_active FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_STORE_CAMPUS_UNAVAILABLE';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('store:'||p_id,0));
 SELECT * INTO s FROM stores WHERE id=p_id FOR UPDATE;
 IF FOUND THEN
  IF s.campus_id<>p_campus THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
  IF p_expected IS NULL THEN
   IF to_jsonb(s)-ARRAY['id','campus_id','created_at','updated_at']=p_data THEN RETURN to_jsonb(s);END IF;
   RAISE EXCEPTION 'HG_STORE_CONFLICT';
  END IF;
  IF s.updated_at<>p_expected THEN RAISE EXCEPTION 'HG_STORE_CONFLICT';END IF;
  before_row:=to_jsonb(s);
  UPDATE stores SET name=p_data->>'name',slug=p_data->>'slug',address=p_data->>'address',instructions=p_data->>'instructions',
   lat=(p_data->>'lat')::float8,lon=(p_data->>'lon')::float8,is_active=(p_data->>'is_active')::boolean,
   pickup_enabled=(p_data->>'pickup_enabled')::boolean,delivery_enabled=(p_data->>'delivery_enabled')::boolean,updated_at=clock_timestamp() WHERE id=p_id RETURNING * INTO s;
 ELSE
  IF p_expected IS NOT NULL THEN RAISE EXCEPTION 'HG_STORE_NOT_FOUND';END IF;
  INSERT INTO stores(id,campus_id,name,slug,address,instructions,lat,lon,is_active,pickup_enabled,delivery_enabled)
  VALUES(p_id,p_campus,p_data->>'name',p_data->>'slug',p_data->>'address',p_data->>'instructions',(p_data->>'lat')::float8,(p_data->>'lon')::float8,
   (p_data->>'is_active')::boolean,(p_data->>'pickup_enabled')::boolean,(p_data->>'delivery_enabled')::boolean) RETURNING * INTO s;
 END IF;
 SELECT role::text INTO actor_role FROM profiles WHERE id=p_actor;
 INSERT INTO admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value,campus_id)
 VALUES(p_actor,actor_role,'stores',p_id::text,'save_store',before_row,to_jsonb(s),p_campus);
 RETURN to_jsonb(s);
END $$;
REVOKE ALL ON FUNCTION public.hg_save_store(uuid,uuid,uuid,jsonb,timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_save_store(uuid,uuid,uuid,jsonb,timestamptz) TO service_role;

CREATE FUNCTION public.hg_set_store_staff(p_actor uuid,p_store uuid,p_users uuid[],p_expected timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE s public.stores;actor_role text;before_row jsonb;
BEGIN
 SELECT * INTO s FROM stores WHERE id=p_store FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_STORE_NOT_FOUND';END IF;
 IF NOT hg_internal.may_manage_store_scope(p_actor,s.campus_id) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 IF s.updated_at IS DISTINCT FROM p_expected THEN RAISE EXCEPTION 'HG_STORE_CONFLICT';END IF;
 IF p_users IS NULL OR cardinality(p_users)>100 OR (SELECT count(DISTINCT x) FROM unnest(p_users)x)<>cardinality(p_users) THEN RAISE EXCEPTION 'HG_STORE_STAFF_INVALID';END IF;
 -- Fresh role/campus lookup: stale memberships never grant store operations.
 PERFORM 1 FROM profiles WHERE id=ANY(p_users) ORDER BY id FOR SHARE;
 IF (SELECT count(*) FROM profiles WHERE id=ANY(p_users) AND is_active AND campus_id=s.campus_id AND role::text IN('kitchen','rider'))<>cardinality(p_users) THEN RAISE EXCEPTION 'HG_STORE_STAFF_INVALID';END IF;
 SELECT coalesce(jsonb_agg(user_id),'[]') INTO before_row FROM hg_internal.store_staff WHERE store_id=p_store;
 DELETE FROM hg_internal.store_staff WHERE store_id=p_store;
 INSERT INTO hg_internal.store_staff(store_id,user_id,assigned_by) SELECT p_store,x,p_actor FROM unnest(p_users)x;
 UPDATE stores SET updated_at=clock_timestamp() WHERE id=p_store RETURNING * INTO s;
 SELECT role::text INTO actor_role FROM profiles WHERE id=p_actor;
 INSERT INTO admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value,campus_id)
 VALUES(p_actor,actor_role,'stores',p_store::text,'set_store_staff',before_row,to_jsonb(p_users),s.campus_id);
 RETURN to_jsonb(s);
END $$;
REVOKE ALL ON FUNCTION public.hg_set_store_staff(uuid,uuid,uuid[],timestamptz) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_set_store_staff(uuid,uuid,uuid[],timestamptz) TO service_role;

CREATE FUNCTION public.hg_store_staff(p_actor uuid,p_store uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE c uuid;
BEGIN
 SELECT campus_id INTO c FROM stores WHERE id=p_store;
 IF c IS NULL OR NOT hg_internal.may_manage_store_scope(p_actor,c) THEN RAISE EXCEPTION 'HG_STORE_ACCESS' USING ERRCODE='42501';END IF;
 RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('id',p.id,'name',coalesce(p.full_name,p.nickname,p.email),'email',p.email,'role',p.role,'is_active',p.is_active,'eligible',p.is_active AND p.campus_id=c AND p.role::text IN('kitchen','rider')) ORDER BY p.full_name,p.email)
 FROM hg_internal.store_staff m JOIN profiles p ON p.id=m.user_id WHERE m.store_id=p_store),'[]');
END $$;
REVOKE ALL ON FUNCTION public.hg_store_staff(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_store_staff(uuid,uuid) TO service_role;

-- A visible off flag must not allow an incomplete fulfilment cutover.
INSERT INTO feature_flags(feature_name,is_active,description,campus_id)
 SELECT 'multi_store_ordering',false,'Store-specific fulfilment; activation waits for the complete ordering cutover.',NULL
 WHERE NOT EXISTS(SELECT 1 FROM feature_flags WHERE feature_name='multi_store_ordering' AND campus_id IS NULL);
CREATE FUNCTION hg_internal.guard_multi_store_activation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
BEGIN
 IF NEW.feature_name='multi_store_ordering' AND NEW.is_active THEN RAISE EXCEPTION 'HG_STORE_CUTOVER_NOT_READY' USING ERRCODE='23514';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION hg_internal.guard_multi_store_activation() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.guard_multi_store_activation() TO service_role;
CREATE TRIGGER multi_store_cutover_guard BEFORE INSERT OR UPDATE ON feature_flags FOR EACH ROW EXECUTE FUNCTION hg_internal.guard_multi_store_activation();
NOTIFY pgrst,'reload schema';
