-- Fresh actors/configuration only. No genuine account, stock or provider mutation.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();actor uuid:=gen_random_uuid();student uuid:=gen_random_uuid();super_id uuid:=gen_random_uuid();
 decimal_item uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();foreign_meal uuid:=gen_random_uuid();punit uuid;uunit uuid;receipt uuid:=gen_random_uuid();n integer;row record;role_name text;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Ingredient A','audit-ingredient-'||ca),(cb,'[AUDIT rollback] Ingredient B','audit-ingredient-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES
 (actor,'audit-stock-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Ingredient admin"}'),
 (student,'audit-stock-'||student||'@example.invalid','{"full_name":"[AUDIT rollback] Ingredient student"}'),
 (super_id,'audit-stock-'||super_id||'@example.invalid','{"full_name":"[AUDIT rollback] Ingredient super"}');
 UPDATE public.profiles SET campus_id=ca,role='admin' WHERE id=actor;
 UPDATE public.profiles SET campus_id=ca,role='student' WHERE id=student;
 UPDATE public.profiles SET campus_id=ca,role='super_admin' WHERE id=super_id;
 SELECT id INTO punit FROM public.measurement_units ORDER BY id LIMIT 1;
 SELECT id INTO uunit FROM public.measurement_units WHERE id<>punit ORDER BY id LIMIT 1;
 IF uunit IS NULL THEN RAISE EXCEPTION 'two configured units required'; END IF;
 INSERT INTO public.stock_items(id,campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold) VALUES
 (foreign_meal,cb,'[AUDIT rollback] Ingredient',punit,uunit,2,3);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 INSERT INTO public.stock_items(id,campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold) VALUES(meal,ca,'[AUDIT rollback] Ingredient',punit,uunit,2,3);
 IF EXISTS(SELECT 1 FROM public.stock_items WHERE id=foreign_meal) THEN RAISE EXCEPTION 'foreign stock visible to campus admin';END IF;
 BEGIN
  INSERT INTO public.stock_items(campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold) VALUES(ca,'  [AUDIT ROLLBACK] ingredient  ',punit,uunit,2,3);
  RAISE EXCEPTION 'duplicate ingredient name accepted';
 EXCEPTION WHEN unique_violation THEN NULL;END;
 BEGIN
  INSERT INTO public.stock_items(campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold,current_balance) VALUES(ca,'[AUDIT rollback] Illegal opening',punit,uunit,2,3,5);
  RAISE EXCEPTION 'unrecorded opening balance accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN UPDATE public.stock_items SET current_balance=500 WHERE id=meal;RAISE EXCEPTION 'direct balance tamper accepted';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN DELETE FROM public.stock_items WHERE id=meal;RAISE EXCEPTION 'direct item deletion accepted';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN
  INSERT INTO public.stock_ledger(stock_item_id,campus_id,type,quantity_entered,unit_id,quantity_in_usage_units,logged_by) VALUES(meal,ca,'purchase',5,punit,10,actor);
  RAISE EXCEPTION 'direct ledger insertion accepted';
 EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 UPDATE public.stock_items SET low_stock_threshold=4 WHERE id=meal;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'authorized metadata update blocked';END IF;
 IF has_function_privilege('authenticated','public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid)','execute') OR has_function_privilege('anon','public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid)','execute') OR NOT has_function_privilege('service_role','public.hg_adjust_stock_balance(uuid,text,numeric,numeric,uuid,numeric,text,uuid,uuid)','execute') THEN RAISE EXCEPTION 'adjustment execution grants incorrect';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 INSERT INTO public.stock_items(id,campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold) VALUES(decimal_item,ca,'[AUDIT rollback] Decimal ingredient',punit,uunit,3,0);
 SELECT * INTO row FROM public.hg_adjust_stock_balance(decimal_item,'purchase',0.1,0.3,punit,0.2,'decimal conversion',actor,gen_random_uuid());
 IF row.new_balance<>0.3 THEN RAISE EXCEPTION 'decimal conversion lost precision';END IF;
 SELECT * INTO row FROM public.hg_adjust_stock_balance(meal,'purchase',5,10,punit,20,'Receipt 01',actor,receipt);IF row.new_balance<>10 THEN RAISE EXCEPTION 'purchase conversion wrong';END IF;
 PERFORM public.hg_adjust_stock_balance(meal,'purchase',5,10,punit,20,'Receipt 01',actor,receipt);
 IF (SELECT count(*) FROM public.stock_ledger WHERE stock_item_id=meal)<>1 THEN RAISE EXCEPTION 'purchase replay duplicated ledger';END IF;
 PERFORM public.hg_adjust_stock_balance(meal,'correction',-3,3,uunit,null,'add stock',actor,gen_random_uuid());
 PERFORM public.hg_adjust_stock_balance(meal,'waste',2,-2,uunit,null,'waste',actor,gen_random_uuid());
 PERFORM public.hg_adjust_stock_balance(meal,'usage',1,-1,uunit,null,'usage',actor,gen_random_uuid());
 PERFORM public.hg_adjust_stock_balance(meal,'correction',4,-4,uunit,null,'remove stock',actor,gen_random_uuid());
 IF (SELECT current_balance FROM public.stock_items WHERE id=meal)<>6 OR (SELECT count(*) FROM public.stock_ledger WHERE stock_item_id=meal)<>5 THEN RAISE EXCEPTION 'signed adjustment conservation failed';END IF;
 IF NOT EXISTS(SELECT 1 FROM public.stock_ledger WHERE id=receipt AND quantity_entered=5 AND quantity_in_usage_units=10 AND unit_id=punit AND cost=20) THEN RAISE EXCEPTION 'entered unit/cost not preserved';END IF;
 BEGIN PERFORM public.hg_adjust_stock_balance(meal,'usage',100,-100,uunit,null,null,actor,gen_random_uuid());RAISE EXCEPTION 'overdraw accepted';EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN PERFORM public.hg_adjust_stock_balance(foreign_meal,'usage',1,-1,uunit,null,null,actor,gen_random_uuid());RAISE EXCEPTION 'foreign adjustment accepted';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 IF (SELECT current_balance FROM public.stock_items WHERE id=meal)<>6 OR (SELECT count(*) FROM public.stock_ledger WHERE stock_item_id=meal)<>5 THEN RAISE EXCEPTION 'refused adjustment wrote data';END IF;
 FOR role_name IN SELECT unnest(ARRAY['student','kitchen','rider']) LOOP
  UPDATE public.profiles SET role=role_name::public.user_role WHERE id=student;
  PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',student)::text,true);PERFORM set_config('role','authenticated',true);
  IF EXISTS(SELECT 1 FROM public.stock_items WHERE id=meal) OR EXISTS(SELECT 1 FROM public.stock_ledger WHERE stock_item_id=meal) THEN RAISE EXCEPTION 'non-admin stock read exposed';END IF;
  UPDATE public.stock_items SET name='forbidden' WHERE id=meal;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'non-admin metadata update accepted';END IF;
  PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 END LOOP;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',super_id)::text,true);PERFORM set_config('role','authenticated',true);
 IF (SELECT count(*) FROM public.stock_items WHERE id IN(meal,foreign_meal))<>2 THEN RAISE EXCEPTION 'super admin cannot read both campuses';END IF;
 PERFORM set_config('role','none',true);
END $verify$;
ROLLBACK;
SELECT 'PASS: fresh rollback actors; scoped create/read/name uniqueness; direct balance/ledger tamper denied; private adjustment grants, unit conversion, replay, signed corrections, waste/usage/overdraw and role isolation' AS evidence;
