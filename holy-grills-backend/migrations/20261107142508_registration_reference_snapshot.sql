-- One read-only snapshot avoids serial campus/department/level HTTP requests.
CREATE OR REPLACE FUNCTION public.hg_registration_options(p_campus_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = public AS $$
DECLARE
  v_campuses jsonb;
  v_campus uuid := p_campus_id;
  v_departments jsonb := '[]'::jsonb;
  v_levels jsonb := '[]'::jsonb;
BEGIN
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'name',name,'slug',slug,
    'lat',lat,'lon',lon,'is_default',is_default) ORDER BY name), '[]'::jsonb)
    INTO v_campuses FROM public.campuses WHERE is_active;
  IF v_campus IS NULL AND jsonb_array_length(v_campuses) = 1 THEN
    v_campus := (v_campuses->0->>'id')::uuid;
  END IF;
  IF v_campus IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM public.campuses WHERE id=v_campus AND is_active
  ) THEN
    RETURN jsonb_build_object('error','campus_unavailable','campuses',v_campuses);
  END IF;
  IF v_campus IS NOT NULL THEN
    SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY d.sort_order,d.name),'[]'::jsonb)
    INTO v_departments FROM (
      SELECT DISTINCT ON (lower(trim(name))) id,name,faculty,slug,sort_order,campus_id
      FROM public.departments WHERE is_active AND (campus_id=v_campus OR campus_id IS NULL)
      ORDER BY lower(trim(name)),campus_id NULLS LAST,id
    ) d;
    SELECT coalesce(jsonb_agg(to_jsonb(l) ORDER BY l.sort_order,l.name),'[]'::jsonb)
    INTO v_levels FROM (
      SELECT DISTINCT ON (value) id,name,value,rank,sort_order,campus_id
      FROM public.academic_levels WHERE is_active AND (campus_id=v_campus OR campus_id IS NULL)
      ORDER BY value,campus_id NULLS LAST,id
    ) l;
  END IF;
  RETURN jsonb_build_object('campus_id',v_campus,'campuses',v_campuses,
    'departments',v_departments,'levels',v_levels);
END $$;
REVOKE ALL ON FUNCTION public.hg_registration_options(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.hg_registration_options(uuid) TO service_role;
