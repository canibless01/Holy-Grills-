-- Run after the migration, or splice it inside this BEGIN when testing DDL.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $$
DECLARE c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();d uuid:=gen_random_uuid();w uuid:=gen_random_uuid();off_user uuid:=gen_random_uuid();u uuid;r jsonb;
BEGIN
 INSERT INTO public.campuses(id,name,slug,is_active) VALUES(c,'[AUDIT rollback] Balance notices','audit-'||c,true);
 FOREACH u IN ARRAY ARRAY[a,b,d,w,off_user] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-balance-'||u||'@example.invalid','{}');
  UPDATE profiles SET campus_id=c,is_active=true,push_enabled=true WHERE id=u;
  INSERT INTO notification_preferences(user_id,campus_id,hp_updates,push_enabled) VALUES(u,c,true,true) ON CONFLICT(user_id) DO UPDATE SET hp_updates=true,push_enabled=true;
 END LOOP;
 PERFORM set_config('hg.audit_balance_users',jsonb_build_object('a',a,'b',b,'d',d,'w',w,'off',off_user)::text,true);
 r:=public.record_hp_transaction_atomic(a,50,'earn','active','referral','referral',gen_random_uuid(),null,'Referral',c);IF r ? 'error' THEN RAISE EXCEPTION '%',r;END IF;
 r:=public.record_hp_transaction_atomic(a,25,'earn','active','food_order','order',gen_random_uuid(),null,'Delivery',c);IF r ? 'error' THEN RAISE EXCEPTION '%',r;END IF;
 UPDATE profiles SET hp_balance=10 WHERE id=b;UPDATE profiles SET hp_balance=0 WHERE id=b;
 r:=public.record_hp_transaction_atomic(d,40,'earn','pending','social','social',gen_random_uuid(),null,'Pending',c);IF r ? 'error' THEN RAISE EXCEPTION '%',r;END IF;
 INSERT INTO wallets(user_id,campus_id,balance,currency) VALUES(w,c,0,'NGN') ON CONFLICT(user_id) DO NOTHING;
 UPDATE wallets SET balance=100 WHERE user_id=w;UPDATE wallets SET balance=50 WHERE user_id=w;
 UPDATE notification_preferences SET hp_updates=false WHERE user_id=off_user;UPDATE profiles SET hp_balance=20 WHERE id=off_user;
 BEGIN UPDATE profiles SET hp_balance=999 WHERE id=b;RAISE EXCEPTION 'interrupted action';EXCEPTION WHEN OTHERS THEN NULL;END;
END $$;
SET CONSTRAINTS ALL IMMEDIATE;
DO $$
DECLARE ids jsonb:=current_setting('hg.audit_balance_users')::jsonb;n integer;
BEGIN
 SELECT count(*) INTO n FROM notifications WHERE user_id=(ids->>'a')::uuid AND type='hp_balance_changed';IF n<>2 THEN RAISE EXCEPTION 'Expected one HP notice per channel, got %',n;END IF;
 IF EXISTS(SELECT 1 FROM notifications WHERE user_id=(ids->>'a')::uuid AND type='hp_balance_changed' AND (metadata->>'delta')::numeric<>75) THEN RAISE EXCEPTION 'Notice missed net committed HP';END IF;
 IF EXISTS(SELECT 1 FROM notifications WHERE user_id=(ids->>'b')::uuid AND type='hp_balance_changed') THEN RAISE EXCEPTION 'Net-zero/rolled-back work sent a notice';END IF;
 SELECT count(*) INTO n FROM notifications WHERE user_id=(ids->>'d')::uuid AND type='hp_balance_changed' AND metadata->>'pending'='true' AND (metadata->>'delta')::numeric=40;IF n<>2 THEN RAISE EXCEPTION 'Pending destination not recorded';END IF;
 SELECT count(*) INTO n FROM notifications WHERE user_id=(ids->>'w')::uuid AND type='wallet_balance_changed' AND (metadata->>'delta')::numeric=50;IF n<>2 THEN RAISE EXCEPTION 'Wallet net delta incorrect: %',n;END IF;
 IF EXISTS(SELECT 1 FROM notifications WHERE user_id=(ids->>'off')::uuid AND type='hp_balance_changed') THEN RAISE EXCEPTION 'HP preference ignored';END IF;
 SELECT count(*) INTO n FROM notification_deliveries WHERE user_id=(ids->>'a')::uuid AND channel='push';IF n<>1 THEN RAISE EXCEPTION 'Durable push not saved';END IF;
 IF has_function_privilege('authenticated','hg_internal.save_balance_activity(uuid,text,uuid,numeric,boolean,jsonb,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'Balance helper browser privilege';END IF;
END $$;
ROLLBACK;
