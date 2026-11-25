BEGIN;
SET LOCAL search_path=public,extensions;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $test$
DECLARE c uuid:=gen_random_uuid();other_c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();k uuid:=gen_random_uuid();outsider uuid:=gen_random_uuid();
 s uuid:=gen_random_uuid();s2 uuid:=gen_random_uuid();foreign_s uuid:=gen_random_uuid();i uuid:=gen_random_uuid();ingredient uuid:=gen_random_uuid();
 unit uuid:=gen_random_uuid();rid uuid:=gen_random_uuid();body jsonb;result jsonb;balance numeric;v timestamptz;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[ROLLBACK] Supplies',c::text),(other_c,'[ROLLBACK] Other supplies',other_c::text);
 INSERT INTO auth.users(id,email,raw_user_meta_data) SELECT x,'supplies-'||x||'@example.invalid','{}' FROM unnest(ARRAY[a,k,outsider])x;
 UPDATE profiles SET role='admin',campus_id=c,is_active=true WHERE id=a;
 UPDATE profiles SET role='kitchen',campus_id=c,is_active=true WHERE id=k;
 UPDATE profiles SET role='admin',campus_id=other_c,is_active=true WHERE id=outsider;
 INSERT INTO stores(id,campus_id,name,slug,address) VALUES(s,c,'Counter A',s::text,'Counter A road'),(s2,c,'Counter B',s2::text,'Counter B road'),(foreign_s,other_c,'Other campus',foreign_s::text,'Other road');
 INSERT INTO hg_internal.store_staff(store_id,user_id,assigned_by) VALUES(s,k,a);
 INSERT INTO measurement_units(id,name) VALUES(unit,'audit-unit-'||unit);
 INSERT INTO stock_items(id,campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold)
 VALUES(i,c,'[ROLLBACK] Containers',unit,unit,10,2),(ingredient,c,'[ROLLBACK] Central flour',unit,unit,10,2);
 PERFORM hg_adjust_stock_balance(i,'purchase',10,100,unit,2000,'Receipt at central kitchen',a,gen_random_uuid());
 PERFORM hg_adjust_stock_balance(ingredient,'purchase',10,100,unit,2000,'Central ingredient',a,gen_random_uuid());
 BEGIN
  PERFORM hg_store_stock(a,c,NULL,'transfer',jsonb_build_object('item_id',ingredient,'request_id',rid,'quantity',10,'notes','Not distributable','destination_store_id',s));
  RAISE EXCEPTION 'central ingredient was allocated';
 EXCEPTION WHEN check_violation THEN NULL;END;
 PERFORM hg_store_stock(a,c,NULL,'classify',jsonb_build_object('item_id',i,'distributable',true));
 body:=jsonb_build_object('item_id',i,'request_id',rid,'quantity',60,'notes','Dispatch containers','destination_store_id',s);
 PERFORM hg_store_stock(a,c,NULL,'transfer',body);
 result:=hg_store_stock(a,c,NULL,'transfer',body);
 IF result->>'replayed'<>'true' OR (SELECT count(*) FROM stock_ledger WHERE store_transfer_id=rid)<>2 THEN RAISE EXCEPTION 'transfer replay duplicated stock';END IF;
 IF (SELECT current_balance FROM stock_items WHERE id=i)<>100 THEN RAISE EXCEPTION 'internal transfer changed campus total';END IF;
 result:=hg_store_stock(a,c,s,'snapshot');
 IF (result->'items'->0->>'store_balance')::numeric<>60 OR (result->'items'->0->>'central_balance')::numeric<>40 THEN RAISE EXCEPTION 'allocation report incorrect';END IF;
 BEGIN PERFORM hg_store_stock(a,c,NULL,'transfer',body||'{"quantity":61}');RAISE EXCEPTION 'changed replay accepted';EXCEPTION WHEN unique_violation THEN NULL;END;
 BEGIN PERFORM hg_store_stock(a,c,NULL,'classify',jsonb_build_object('item_id',i,'distributable',false));RAISE EXCEPTION 'allocated supplies reclassified';EXCEPTION WHEN object_not_in_prerequisite_state THEN NULL;END;
 BEGIN UPDATE stock_items SET store_distributable=false WHERE id=i;RAISE EXCEPTION 'classification guard bypassed';EXCEPTION WHEN object_not_in_prerequisite_state THEN NULL;END;
 BEGIN PERFORM hg_adjust_stock_balance(i,'usage',41,-41,unit,NULL,'Cannot consume store allocation',a,gen_random_uuid());RAISE EXCEPTION 'central usage stole store stock';EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN PERFORM hg_store_stock(a,c,NULL,'transfer',body||jsonb_build_object('request_id',gen_random_uuid(),'quantity',41));RAISE EXCEPTION 'central transfer overdrew';EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN PERFORM hg_store_stock(outsider,c,s,'snapshot');RAISE EXCEPTION 'cross campus read';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_store_stock(k,c,s2,'snapshot');RAISE EXCEPTION 'cross store read';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_store_stock(k,c,NULL,'snapshot');RAISE EXCEPTION 'kitchen read central balance';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 result:=hg_store_stock(k,c,s,'snapshot');
 IF result->'items'->0 ? 'current_balance' OR result->'items'->0 ? 'central_balance' THEN RAISE EXCEPTION 'store kitchen exposed campus quantities';END IF;
 BEGIN PERFORM hg_store_stock(a,c,s,'transfer',body||jsonb_build_object('request_id',gen_random_uuid(),'destination_store_id',foreign_s));RAISE EXCEPTION 'foreign transfer accepted';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 rid:=gen_random_uuid();body:=jsonb_build_object('item_id',i,'request_id',rid,'quantity',15,'notes','Served orders');
 PERFORM hg_store_stock(k,c,s,'usage',body);PERFORM hg_store_stock(k,c,s,'usage',body);
 IF (SELECT current_balance FROM stock_items WHERE id=i)<>85 THEN RAISE EXCEPTION 'usage replay affected campus total twice';END IF;
 PERFORM hg_store_stock(a,c,s,'transfer',jsonb_build_object('item_id',i,'request_id',gen_random_uuid(),'quantity',20,'notes','Rebalance counters','destination_store_id',s2));
 PERFORM hg_store_stock(a,c,s2,'waste',jsonb_build_object('item_id',i,'request_id',gen_random_uuid(),'quantity',2,'notes','Damaged packaging'));
 PERFORM hg_store_stock(a,c,s2,'correction',jsonb_build_object('item_id',i,'request_id',gen_random_uuid(),'quantity',1,'notes','Stocktake correction'));
 PERFORM hg_store_stock(a,c,s2,'transfer',jsonb_build_object('item_id',i,'request_id',gen_random_uuid(),'quantity',19,'notes','Return unused containers','destination_store_id',NULL));
 result:=hg_store_stock(a,c,NULL,'snapshot');
 SELECT current_balance INTO balance FROM stock_items WHERE id=i;
 IF balance<>84 OR (SELECT sum(quantity_in_usage_units) FROM stock_ledger WHERE stock_item_id=i)<>balance
  OR (SELECT sum(quantity_in_usage_units) FROM stock_ledger WHERE stock_item_id=i AND store_id=s)<>25
  OR (SELECT sum(quantity_in_usage_units) FROM stock_ledger WHERE stock_item_id=i AND store_id=s2)<>0 THEN RAISE EXCEPTION 'stock conservation failed';END IF;
 BEGIN PERFORM hg_store_stock(k,c,s,'correction',jsonb_build_object('item_id',i,'request_id',gen_random_uuid(),'quantity',10,'notes','Unauthorized adjustment'));RAISE EXCEPTION 'kitchen correction allowed';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 UPDATE profiles SET campus_id=NULL WHERE id=outsider;
 BEGIN PERFORM hg_store_stock(outsider,c,s,'snapshot');RAISE EXCEPTION 'campus-less admin allowed';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 IF has_function_privilege('authenticated','public.hg_store_stock(uuid,uuid,uuid,text,jsonb)','execute') OR has_function_privilege('anon','public.hg_store_stock(uuid,uuid,uuid,text,jsonb)','execute') THEN RAISE EXCEPTION 'client function grant';END IF;
END$test$;
SELECT 'PASS central ingredients, two-store supplies, transfer/usage replay, campus conservation, returns, stocktakes, insufficient stock, central allocation protection and role boundaries' AS verified;
ROLLBACK;
