-- No live store/user/configuration survives this verification.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
SET LOCAL search_path=public,extensions;
DO $test$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();a uuid:=gen_random_uuid();k uuid:=gen_random_uuid();r uuid:=gen_random_uuid();outsider uuid:=gen_random_uuid();
 u uuid:=gen_random_uuid();s uuid:=gen_random_uuid();data jsonb;result jsonb;old_version timestamptz;v timestamptz;count_before integer;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[ROLLBACK] Store campus',c::text),(other_c,'[ROLLBACK] Other campus',other_c::text);
 INSERT INTO auth.users(id,email,raw_user_meta_data) SELECT x,'store-check-'||x||'@example.invalid','{}'::jsonb FROM unnest(ARRAY[sa,a,k,r,outsider])x;
 UPDATE profiles SET role='super_admin',campus_id=c,is_active=true WHERE id=sa;
 UPDATE profiles SET role='admin',campus_id=c,is_active=true WHERE id=a;
 UPDATE profiles SET role='kitchen',campus_id=c,is_active=true WHERE id=k;
 UPDATE profiles SET role='rider',campus_id=c,is_active=true WHERE id=r;
 UPDATE profiles SET role='kitchen',campus_id=other_c,is_active=true WHERE id=outsider;
 data:=jsonb_build_object('name','[ROLLBACK] University','slug',u::text,'is_active',true);
 result:=hg_save_university(sa,u,data,NULL);
 PERFORM hg_save_university(sa,u,data,NULL);
 IF (SELECT count(*) FROM admin_audit_logs WHERE entity_id=u::text AND action='save_university')<>1 THEN RAISE EXCEPTION 'university retry duplicated audit';END IF;
 BEGIN PERFORM hg_save_university(a,gen_random_uuid(),data,NULL);RAISE EXCEPTION 'campus admin changed university';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 SELECT updated_at INTO v FROM campuses WHERE id=c;
 result:=hg_link_university_campus(sa,c,u,v);
 IF (result->>'university_id')::uuid<>u THEN RAISE EXCEPTION 'university link missing';END IF;
 BEGIN PERFORM hg_link_university_campus(sa,c,NULL,v);RAISE EXCEPTION 'stale campus edit accepted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_STORE_CONFLICT' THEN RAISE;END IF;END;
 data:=jsonb_build_object('name','[ROLLBACK] Main store','slug',s::text,'address','West gate road','instructions','Counter collection','lat',7.3,'lon',5.2,'is_active',true,'pickup_enabled',true,'delivery_enabled',true);
 result:=hg_save_store(a,s,c,data,NULL);v:=(result->>'updated_at')::timestamptz;
 PERFORM hg_save_store(a,s,c,data,NULL);
 IF (SELECT count(*) FROM stores WHERE id=s)<>1 OR (SELECT count(*) FROM admin_audit_logs WHERE entity_id=s::text AND action='save_store')<>1 THEN RAISE EXCEPTION 'store retry duplicated data';END IF;
 BEGIN PERFORM hg_save_store(a,gen_random_uuid(),other_c,data,NULL);RAISE EXCEPTION 'cross-campus store created';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 old_version:=v;result:=hg_save_store(a,s,c,data||'{"address":"Updated counter"}',v);v:=(result->>'updated_at')::timestamptz;
 BEGIN PERFORM hg_save_store(a,s,c,data,old_version);RAISE EXCEPTION 'stale store edit accepted';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_STORE_CONFLICT' THEN RAISE;END IF;END;
 result:=hg_set_store_staff(a,s,ARRAY[k,r],v);v:=(result->>'updated_at')::timestamptz;
 IF jsonb_array_length(hg_store_staff(a,s))<>2 THEN RAISE EXCEPTION 'team assignment missing';END IF;
 BEGIN PERFORM hg_set_store_staff(a,s,ARRAY[outsider],v);RAISE EXCEPTION 'cross-campus staff assigned';EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'HG_STORE_STAFF_INVALID' THEN RAISE;END IF;END;
 IF jsonb_array_length(hg_store_staff(a,s))<>2 THEN RAISE EXCEPTION 'rejected team change deleted valid assignment';END IF;
 UPDATE profiles SET role='student' WHERE id=k;
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(hg_store_staff(a,s))x WHERE (x->>'id')::uuid=k AND x->>'eligible'='false') THEN RAISE EXCEPTION 'stale staff role not identified';END IF;
 BEGIN UPDATE feature_flags SET is_active=true WHERE feature_name='multi_store_ordering';RAISE EXCEPTION 'incomplete cutover activated';EXCEPTION WHEN check_violation THEN NULL;END;
 IF has_table_privilege('authenticated','public.stores','select') OR has_table_privilege('anon','public.universities','select')
 OR has_function_privilege('authenticated','public.hg_save_store(uuid,uuid,uuid,jsonb,timestamptz)','execute') THEN RAISE EXCEPTION 'browser gained private store setup access';END IF;
END $test$;
SELECT 'store/university create replay, edit conflicts, campus links, staff role/campus validation, audit atomicity, grants and inactive cutover passed' AS verified;
ROLLBACK;
