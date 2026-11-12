BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.cs_check(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Cushion snapshot: %',label;END IF;END$$;
DO $test$
DECLARE c uuid:=gen_random_uuid();cat uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();bundle uuid:=gen_random_uuid();extra uuid:=gen_random_uuid();vg uuid:=gen_random_uuid();opt uuid:=gen_random_uuid();ag uuid:=gen_random_uuid();oid uuid:=gen_random_uuid();line uuid:=gen_random_uuid();addon_line uuid:=gen_random_uuid();selection uuid:=gen_random_uuid();zero_line uuid:=gen_random_uuid();r text;t text;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Cushion','audit-cushion-'||c);
 INSERT INTO menu_categories(id,name,slug,campus_id) VALUES(cat,'[AUDIT rollback] Cushion','audit-cushion-'||cat,c);
 INSERT INTO menu_items(id,category_id,name,slug,price,cushion_amount,campus_id) VALUES(meal,cat,'[AUDIT rollback] Meal','audit-cushion-'||meal,3500,500,c);
 PERFORM pg_temp.cs_check((SELECT price=3500 AND cushion_amount=500 FROM menu_items WHERE id=meal),'inclusive price stays 3500, not 4000');
 INSERT INTO menu_addon_groups(id,menu_item_id,name,campus_id) VALUES(ag,meal,'[AUDIT rollback] Extras',c);
 INSERT INTO menu_addons(id,name,price,cushion_amount,campus_id,group_id) VALUES(extra,'[AUDIT rollback] Side',400,50,c,ag),(bundle,'[AUDIT rollback] Checkout bundle',1500,100,c,NULL);
 INSERT INTO menu_item_variation_groups(id,menu_item_id,name,campus_id) VALUES(vg,meal,'[AUDIT rollback] Combo',c);
 INSERT INTO menu_item_variation_options(id,variation_group_id,name,price_delta,cushion_amount,campus_id) VALUES(opt,vg,'[AUDIT rollback] Combo choice',1000,200,c);
 INSERT INTO orders(id,campus_id,guest_email,claim_token,status,payment_status,subtotal,delivery_fee,total_amount,card_amount_used) VALUES(oid,c,'audit-cushion-'||oid||'@example.invalid',gen_random_uuid(),'received','pending',12100,500,12600,12600);
 INSERT INTO order_items(id,order_id,menu_item_id,campus_id,name_snapshot,price_snapshot,line_total,quantity,cushion_snapshot,selected_variations)
 VALUES(line,oid,meal,c,'[AUDIT rollback] Meal',5300,10600,2,9999,jsonb_build_array(jsonb_build_object('option_id',opt,'variation_group_id',vg)));
 INSERT INTO order_addon_selections(id,order_item_id,addon_id,group_id,name_snapshot,price_delta_snapshot,quantity,campus_id,cushion_snapshot)
 VALUES(selection,line,extra,ag,'[AUDIT rollback] Side',400,2,c,9999);
 INSERT INTO order_items(id,order_id,addon_id,is_addon,campus_id,name_snapshot,price_snapshot,line_total,quantity,cushion_snapshot)
 VALUES(addon_line,oid,bundle,true,c,'[AUDIT rollback] Checkout bundle',1500,1500,1,9999);
 INSERT INTO order_items(id,order_id,menu_item_id,campus_id,name_snapshot,price_snapshot,line_total,quantity)
 VALUES(zero_line,oid,meal,c,'[AUDIT rollback] Free reward',0,0,1);
 PERFORM pg_temp.cs_check((SELECT cushion_snapshot=700 FROM order_items WHERE id=line),'base plus combo cushion comes from server catalogue, not client');
 PERFORM pg_temp.cs_check((SELECT cushion_snapshot=50 FROM order_addon_selections WHERE id=selection),'selected addon has its own per-unit snapshot');
 PERFORM pg_temp.cs_check((SELECT cushion_snapshot=100 FROM order_items WHERE id=addon_line),'checkout bundle snapshot captured');
 PERFORM pg_temp.cs_check((SELECT cushion_snapshot=0 FROM order_items WHERE id=zero_line),'free reward does not create fictional cushion income');
 PERFORM pg_temp.cs_check((SELECT sum(cushion_snapshot*quantity) FROM order_items WHERE order_id=oid)+(SELECT sum(s.cushion_snapshot*s.quantity*i.quantity) FROM order_addon_selections s JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=oid)=1700,'quantity arithmetic counts selected extras once per parent item');
 UPDATE menu_items SET price=3900,cushion_amount=600 WHERE id=meal;
 UPDATE menu_addons SET cushion_amount=80 WHERE id=extra;
 UPDATE menu_item_variation_options SET cushion_amount=300 WHERE id=opt;
 PERFORM pg_temp.cs_check((SELECT cushion_snapshot=700 AND price_snapshot=5300 FROM order_items WHERE id=line) AND (SELECT cushion_snapshot=50 FROM order_addon_selections WHERE id=selection),'later catalogue edits do not rewrite order history');
 PERFORM pg_temp.cs_check((SELECT subtotal=12100 AND delivery_fee=500 AND total_amount=12600 FROM orders WHERE id=oid),'snapshot capture does not change charged order amounts');
 BEGIN
  UPDATE order_items SET cushion_snapshot=1 WHERE id=line;RAISE EXCEPTION 'mutable snapshot accepted';
 EXCEPTION WHEN check_violation THEN NULL;END;
 BEGIN
  UPDATE menu_items SET cushion_amount=4000 WHERE id=meal;RAISE EXCEPTION 'cushion larger than selling price accepted';
 EXCEPTION WHEN check_violation THEN NULL;END;
 FOREACH t IN ARRAY ARRAY['menu_items','menu_addons','menu_item_variation_options','order_items','order_addon_selections'] LOOP
  FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
   PERFORM pg_temp.cs_check(NOT has_column_privilege(r,'public.'||t,CASE WHEN t LIKE 'order_%' THEN 'cushion_snapshot' ELSE 'cushion_amount' END,'SELECT'),'internal column is not publicly readable');
   PERFORM pg_temp.cs_check(NOT has_column_privilege(r,'public.'||t,CASE WHEN t LIKE 'order_%' THEN 'cushion_snapshot' ELSE 'cushion_amount' END,'UPDATE'),'internal column cannot be browser edited');
  END LOOP;
 END LOOP;
 PERFORM pg_temp.cs_check(has_column_privilege('anon','public.menu_items','price','SELECT') AND has_column_privilege('authenticated','public.order_items','price_snapshot','SELECT'),'existing public/student price access preserved');
END $test$;
ROLLBACK;
SELECT 'passed: inclusive prices, trusted immutable snapshots, combo/bundle/selected-addon quantities, zero-price rewards, history conservation and private column grants; fixtures rolled back' AS evidence;
