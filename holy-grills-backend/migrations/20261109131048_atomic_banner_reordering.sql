-- Rank the complete same-surface cohort, including equal/legacy ranks, in one
-- transaction. Expected values prevent stale tabs from silently undoing edits.
CREATE OR REPLACE FUNCTION public.hg_move_storefront_banner(p_actor uuid,p_section uuid,p_direction integer,p_expected jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public AS $$
DECLARE a public.profiles%rowtype;s public.banners%rowtype;ids uuid[];orders integer[];i integer;j integer;tmp uuid;n integer;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN RAISE EXCEPTION 'HG_STOREFRONT_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO a FROM public.profiles WHERE id=p_actor AND is_active AND role::text IN('admin','super_admin');
 IF NOT FOUND THEN RAISE EXCEPTION 'HG_STOREFRONT_ACCESS' USING ERRCODE='42501';END IF;
 SELECT * INTO s FROM public.banners WHERE id=p_section;
 IF NOT FOUND OR a.role::text<>'super_admin' AND (s.campus_id IS NULL OR s.campus_id IS DISTINCT FROM a.campus_id) THEN RAISE EXCEPTION 'HG_STOREFRONT_ACCESS' USING ERRCODE='42501';END IF;
 IF p_direction NOT IN(-1,1) OR p_direction IS NULL OR jsonb_typeof(p_expected) IS DISTINCT FROM 'array' OR jsonb_array_length(p_expected)>500 THEN RAISE EXCEPTION 'HG_STOREFRONT_INVALID' USING ERRCODE='23514';END IF;
 PERFORM 1 FROM public.banners WHERE campus_id IS NOT DISTINCT FROM s.campus_id AND coalesce(placement,'home')=coalesce(s.placement,'home') ORDER BY id FOR UPDATE;
 SELECT array_agg(id ORDER BY coalesce(sort_order,0),created_at,id) INTO ids FROM public.banners WHERE campus_id IS NOT DISTINCT FROM s.campus_id AND coalesce(placement,'home')=coalesce(s.placement,'home');
 n:=cardinality(ids);
 IF jsonb_array_length(p_expected)<>n OR (SELECT count(DISTINCT x->>'id') FROM jsonb_array_elements(p_expected)x)<>n OR EXISTS(
  SELECT 1 FROM public.banners row WHERE row.id=ANY(ids) AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(p_expected)x WHERE (x->>'id')::uuid=row.id AND coalesce((x->>'sort_order')::integer,0)=coalesce(row.sort_order,0) AND (x->>'updated_at')::timestamptz IS NOT DISTINCT FROM row.updated_at)
 ) THEN RAISE EXCEPTION 'HG_STOREFRONT_STALE' USING ERRCODE='40001';END IF;
 i:=array_position(ids,p_section);j:=i+p_direction;
 IF j<1 OR j>n THEN RETURN jsonb_build_object('moved',false);END IF;
 tmp:=ids[i];ids[i]:=ids[j];ids[j]:=tmp;
 UPDATE public.banners row SET sort_order=ordered.rank-1,updated_at=now() FROM unnest(ids) WITH ORDINALITY ordered(id,rank) WHERE row.id=ordered.id;
 RETURN jsonb_build_object('moved',true,'ids',to_jsonb(ids));
END $$;
REVOKE ALL ON FUNCTION public.hg_move_storefront_banner(uuid,uuid,integer,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_move_storefront_banner(uuid,uuid,integer,jsonb) TO service_role;
