BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.sr_assert(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$BEGIN IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Stock report: %',label;END IF;END$$;
DO $$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();student uuid:=gen_random_uuid();sa uuid:=gen_random_uuid();actor uuid;meal uuid:=gen_random_uuid();foreign_meal uuid:=gen_random_uuid();punit uuid;uunit uuid;request_id uuid:=gen_random_uuid();opening_id uuid:=gen_random_uuid();r jsonb;row jsonb;old_notice uuid;today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Stock A','audit-stock-report-'||ca),(cb,'[AUDIT rollback] Stock B','audit-stock-report-'||cb);
 FOREACH actor IN ARRAY ARRAY[a,b,student,sa] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-stock-report-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Stock"}');
  UPDATE profiles SET campus_id=ca,role='student',push_enabled=true WHERE id=actor;
 END LOOP;
 UPDATE profiles SET role='admin' WHERE id=a;UPDATE profiles SET role='admin',campus_id=cb WHERE id=b;UPDATE profiles SET role='super_admin' WHERE id=sa;
 INSERT INTO notification_preferences(user_id,promotions,push_enabled) VALUES(a,false,true) ON CONFLICT(user_id) DO UPDATE SET promotions=false,push_enabled=true;
 SELECT id INTO punit FROM measurement_units ORDER BY id LIMIT 1;SELECT id INTO uunit FROM measurement_units ORDER BY id OFFSET 1 LIMIT 1;
 IF punit IS NULL OR uunit IS NULL THEN RAISE EXCEPTION 'measurement units required';END IF;
 INSERT INTO stock_items(id,campus_id,name,purchase_unit_id,usage_unit_id,conversion_factor,low_stock_threshold)
 VALUES(meal,ca,'[AUDIT rollback] Rice',punit,uunit,2,3),(foreign_meal,cb,'[AUDIT rollback] Foreign',punit,uunit,2,3);
 PERFORM hg_adjust_stock_balance(meal,'purchase',3,6,punit,60,'opening',a,opening_id);
 UPDATE stock_ledger SET created_at='2000-01-01T00:00:00Z' WHERE id=opening_id;
 PERFORM hg_adjust_stock_balance(meal,'purchase',2,4,punit,40,'purchase',a,gen_random_uuid());
 PERFORM hg_adjust_stock_balance(meal,'usage',3,-3,uunit,NULL,'usage',a,gen_random_uuid());
 PERFORM hg_adjust_stock_balance(meal,'waste',1,-1,uunit,NULL,'waste',a,gen_random_uuid());
 PERFORM hg_adjust_stock_balance(meal,'correction',-2,2,uunit,NULL,'correction',a,gen_random_uuid());
 PERFORM hg_adjust_stock_balance(meal,'usage',6,-6,uunit,NULL,'low',a,request_id);
 SELECT id INTO old_notice FROM notifications WHERE user_id=a AND reference_id=meal AND channel='push';
 PERFORM pg_temp.sr_assert(hg_stock_low_notice_valid(old_notice),'new low notice valid');
 PERFORM pg_temp.sr_assert((SELECT count(*)=2 FROM notifications WHERE user_id=a AND type='low_stock_ingredient' AND reference_id=meal),'one inbox/push pair captured');
 PERFORM pg_temp.sr_assert((SELECT count(*)=1 FROM notification_deliveries WHERE user_id=a AND channel='push' AND dispatch->>'state'='queued'),'push intent survives before Python returns');
 PERFORM hg_adjust_stock_balance(meal,'usage',6,-6,uunit,NULL,'low',a,request_id);
 PERFORM hg_adjust_stock_balance(meal,'usage',1,-1,uunit,NULL,'still low',a,gen_random_uuid());
 PERFORM pg_temp.sr_assert((SELECT count(*)=2 FROM notifications WHERE user_id=a AND type='low_stock_ingredient' AND reference_id=meal),'retries and further low usage do not spam');
 PERFORM hg_adjust_stock_balance(meal,'purchase',3,6,punit,NULL,'restock',a,gen_random_uuid());
 PERFORM pg_temp.sr_assert(NOT hg_stock_low_notice_valid(old_notice),'replenishment invalidates old episode');
 r:=hg_claim_notification_dispatch_v2(old_notice);
 PERFORM pg_temp.sr_assert(NOT hg_begin_notification_dispatch(old_notice,(r->>'token')::uuid,'{}'),'last send boundary refuses replenished stock');
 PERFORM hg_adjust_stock_balance(meal,'usage',5,-5,uunit,NULL,'low again',a,gen_random_uuid());
 PERFORM pg_temp.sr_assert((SELECT count(*)=4 FROM notifications WHERE user_id=a AND type='low_stock_ingredient' AND reference_id=meal),'restocking rearms next low episode');
 BEGIN PERFORM hg_adjust_stock_balance(meal,'usage',99,-99,uunit,NULL,'invalid',a,gen_random_uuid());RAISE EXCEPTION 'missing overdraw rejection';EXCEPTION WHEN check_violation THEN NULL;END;
 PERFORM pg_temp.sr_assert(NOT EXISTS(SELECT 1 FROM notifications WHERE user_id=b AND reference_id=meal),'other campus admin excluded');
 PERFORM set_config('role','service_role',true);r:=hg_stock_report(a,ca,today,today);PERFORM set_config('role','none',true);
 SELECT value INTO row FROM jsonb_array_elements(r->'items') WHERE value->>'id'=meal::text;
 PERFORM pg_temp.sr_assert((row->>'opening')::numeric=6 AND (row->>'purchased')::numeric=10 AND (row->>'used')::numeric=15 AND (row->>'wasted')::numeric=1 AND (row->>'corrected')::numeric=2 AND (row->>'closing')::numeric=2,'populated period conservation');
 PERFORM pg_temp.sr_assert((row->>'current_balance')::numeric=2 AND (row->>'ledger_balance')::numeric=2 AND (row->>'drift')::numeric=0 AND (row->>'purchase_cost')::numeric=40 AND (row->>'uncosted_purchases')::integer=1,'current reconciliation and unknown costs');
 PERFORM pg_temp.sr_assert(jsonb_array_length(r->'items')=1,'campus data isolated');
 BEGIN PERFORM hg_stock_report(a,cb,today,today);RAISE EXCEPTION 'missing campus denial';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 BEGIN PERFORM hg_stock_report(student,ca,today,today);RAISE EXCEPTION 'missing role denial';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 r:=hg_stock_report(sa,NULL,today,today);
 PERFORM pg_temp.sr_assert(EXISTS(SELECT 1 FROM jsonb_array_elements(r->'items') x WHERE x->>'id'=foreign_meal::text),'super admin all campuses');
 -- A real authenticated threshold edit also captures private push work.
 UPDATE stock_items SET low_stock_threshold=0 WHERE id=meal;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',a)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE stock_items SET low_stock_threshold=3 WHERE id=meal;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 PERFORM pg_temp.sr_assert((SELECT count(*)=3 FROM notification_deliveries WHERE user_id=a AND channel='push'),'authenticated edits retain durable push receipt');
 PERFORM pg_temp.sr_assert(NOT has_function_privilege('authenticated','public.hg_stock_report(uuid,uuid,date,date)','execute') AND NOT has_table_privilege('authenticated','hg_internal.stock_low_episodes','SELECT'),'private report and episode state');
END$$;
ROLLBACK;
SELECT 'passed: populated stock opening/movement/closing/current reconciliation, missing-cost distinction, scope/role boundaries, durable low-stock episode, replay suppression, replenishment rearm and authenticated metadata capture; all fixtures rolled back' evidence;
