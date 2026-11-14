-- Financial reward recovery only: no provider calls or persistent fixtures.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE ids uuid[]; owner_id uuid; a uuid; b uuid; c uuid:=gen_random_uuid(); oid uuid:=gen_random_uuid(); second_id uuid:=gen_random_uuid(); legacy_id uuid:=gen_random_uuid();
 r jsonb; plan jsonb; notes jsonb:='{"welcome":"[AUDIT rollback] Welcome","squad_split":"[AUDIT rollback] Split","squad_bonus":"[AUDIT rollback] Bonus"}';
 p1 uuid:=gen_random_uuid();p2 uuid:=gen_random_uuid();p3 uuid:=gen_random_uuid(); welcome integer; owner_balance integer; ledger_count integer;
BEGIN
 SELECT array_agg(id) INTO ids FROM (SELECT p.id FROM public.profiles p LEFT JOIN public.campuses cp ON cp.id=p.campus_id
 WHERE p.full_name ILIKE '%audit%' AND p.is_active AND coalesce(cp.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 3) q;
 owner_id:=ids[1];a:=ids[2];b:=ids[3];IF b IS NULL THEN RAISE EXCEPTION 'isolated audit actors required'; END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Reward recovery','audit-recover-'||c);
 UPDATE public.profiles SET role='student',campus_id=c,hp_balance=0,next_order_hp_multiplier=1 WHERE id=ANY(ids);
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount,is_squad_order) VALUES(oid,owner_id,c,'delivered','paid',2000,2000,true);
 INSERT INTO public.squad_members(order_id,user_id,email,is_registered,campus_id) VALUES(oid,a,'audit-a@example.invalid',true,c),(oid,b,'audit-b@example.invalid',true,c),(oid,NULL,'audit-guest@example.invalid',false,c);
 r:=public.record_hp_transaction_atomic(owner_id,50,'earn','pending','audit_pending','audit_recovery',p1,NULL,'[AUDIT rollback] Pending A',c);
 r:=public.record_hp_transaction_atomic(owner_id,100,'earn','pending','audit_pending','audit_recovery',p2,NULL,'[AUDIT rollback] Pending B',c);
 UPDATE public.hp_transactions SET created_at='1901-01-01T00:00:00Z' WHERE reference_id=p1;
 UPDATE public.hp_transactions SET created_at='1901-01-02T00:00:00Z' WHERE reference_id=p2;
 r:=public.hg_credit_delivery_hp_atomic(oid,owner_id,26,'ember','food_order',1,101);
 IF NOT coalesce((r->>'success')::boolean,false) THEN RAISE EXCEPTION 'primary award failed: %',r; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=owner_id)<>26 THEN RAISE EXCEPTION 'owner primary share incorrect'; END IF;
 plan:=jsonb_build_object('unlock_amount',70,'welcome_amount',100,'squad_bonus',30,'members',jsonb_build_array(
 jsonb_build_object('user_id',a,'email','audit-a@example.invalid','hp',25),jsonb_build_object('user_id',b,'email','audit-b@example.invalid','hp',25),jsonb_build_object('email','audit-guest@example.invalid','hp',25)));
 UPDATE public.profiles SET is_active=false WHERE id=b;
 r:=public.hg_complete_delivery_rewards_atomic(oid,plan,notes);
 IF r->>'error' IS DISTINCT FROM 'delivery_reward_financial_pending' THEN RAISE EXCEPTION 'failure did not stay pending: %',r; END IF;
 IF (SELECT hp_balance FROM public.profiles WHERE id=owner_id)<>26 OR (SELECT hp_balance FROM public.profiles WHERE id=a)<>0
 OR EXISTS(SELECT 1 FROM public.hp_transactions WHERE reference_id IN(p1,p2) AND status<>'pending')
 OR EXISTS(SELECT 1 FROM public.pending_squad_hp WHERE order_id=oid) THEN RAISE EXCEPTION 'failed auxiliary attempt leaked partial grants'; END IF;
 UPDATE public.profiles SET is_active=true WHERE id=b;
 -- Simulate an already paid member. A retry must finish the other member too.
 r:=public.record_hp_transaction_atomic(a,25,'earn','active','squad_split','squad_split',oid,NULL,'[AUDIT rollback] Existing share',c);
 r:=public.hg_complete_delivery_rewards_atomic(oid,plan||'{"welcome_amount":9999}',notes);
 IF NOT coalesce((r->>'success')::boolean,false) OR (r->>'unlocked_hp')::integer<>70 THEN RAISE EXCEPTION 'recovery did not complete: %',r; END IF;
 welcome:=(r->>'welcome_hp')::integer;
 IF welcome NOT IN(0,100) THEN RAISE EXCEPTION 'retry changed saved welcome terms'; END IF;
 owner_balance:=26+70+welcome+30;
 IF (SELECT hp_balance FROM public.profiles WHERE id=owner_id)<>owner_balance OR (SELECT hp_balance FROM public.profiles WHERE id=a)<>25 OR (SELECT hp_balance FROM public.profiles WHERE id=b)<>25 THEN RAISE EXCEPTION 'recovered balance mismatch'; END IF;
 IF (SELECT count(*) FROM public.hp_transactions WHERE user_id=ANY(ARRAY[a,b]) AND reference_type='squad_split' AND reference_id=oid)<>2 THEN RAISE EXCEPTION 'missing/duplicate squad shares'; END IF;
 IF (SELECT sum(amount) FROM public.hp_transactions WHERE reference_id IN(p1,p2) AND status='pending')<>80 THEN RAISE EXCEPTION 'FIFO pending remainder incorrect'; END IF;
 IF (SELECT amount FROM public.hp_transactions WHERE user_id=owner_id AND reference_type='order_pending_unlock' AND reference_id=oid)<>20 THEN RAISE EXCEPTION 'partial unlock collided or duplicated whole-row amount'; END IF;
 IF (SELECT count(*) FROM public.pending_squad_hp WHERE order_id=oid AND hp_amount=25)<>1 OR NOT(SELECT squad_hp_distributed FROM public.orders WHERE id=oid) THEN RAISE EXCEPTION 'pending share or completion missing'; END IF;
 SELECT count(*) INTO ledger_count FROM public.hp_transactions WHERE reference_id=oid;
 r:=public.record_hp_transaction_atomic(owner_id,10,'earn','pending','audit_pending','audit_recovery',p3,NULL,'[AUDIT rollback] Later pending',c);
 r:=public.hg_complete_delivery_rewards_atomic(oid,plan,notes);
 IF NOT coalesce((r->>'replayed')::boolean,false) OR (SELECT hp_balance FROM public.profiles WHERE id=owner_id)<>owner_balance OR (SELECT count(*) FROM public.hp_transactions WHERE reference_id=oid)<>ledger_count THEN RAISE EXCEPTION 'completion replay changed rewards'; END IF;
 r:=public.unlock_pending_hp_fifo_atomic(owner_id,oid,1000,c);
 IF NOT coalesce((r->>'replayed')::boolean,false) OR (SELECT status FROM public.hp_transactions WHERE reference_id=p3)<>'pending' THEN RAISE EXCEPTION 'unlock replay consumed later pending HP'; END IF;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status) VALUES(second_id,owner_id,c,'delivered','paid');
 r:=public.hg_credit_delivery_hp_atomic(second_id,owner_id,0,'ember','food_order',1,0);
 r:=public.hg_complete_delivery_rewards_atomic(second_id,'{"unlock_amount":0,"welcome_amount":100,"squad_bonus":0,"members":[]}',notes);
 IF NOT coalesce((r->>'success')::boolean,false) OR (r->>'welcome_hp')::integer<>0 THEN RAISE EXCEPTION 'welcome awarded twice'; END IF;
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,hp_credited_at) VALUES(legacy_id,owner_id,c,'delivered','paid',now());
 r:=public.hg_complete_delivery_rewards_atomic(legacy_id,plan,notes);
 IF r->>'error' IS DISTINCT FROM 'legacy_delivery_reward_review_required' THEN RAISE EXCEPTION 'ambiguous legacy order was not refused'; END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',owner_id)::text,true);
 PERFORM set_config('role','authenticated',true);
 IF EXISTS(SELECT 1 FROM public.order_status_logs WHERE order_id=oid AND metadata ?| ARRAY['delivery_reward_recovery','pending_hp_unlock']) THEN RAISE EXCEPTION 'private reward receipt exposed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.orders WHERE id=oid) THEN RAISE EXCEPTION 'owner lost access to ordinary order'; END IF;
 PERFORM set_config('role','none',true);
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF has_function_privilege('authenticated','public.hg_complete_delivery_rewards_atomic(uuid,jsonb,jsonb)','EXECUTE') OR has_function_privilege('anon','public.hg_complete_delivery_rewards_atomic(uuid,jsonb,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'financial recovery exposed'; END IF;
END $audit$;
ROLLBACK;
SELECT 'primary share, atomic auxiliary rollback/recovery, missing squad-member recovery, FIFO full+partial unlock, immutable retry terms, welcome-once and ledger/claim replay passed; fixtures rolled back' AS evidence;
