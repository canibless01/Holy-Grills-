-- Rolled-back native proof. Requires all three 20 October marketplace migrations.
-- Every inserted row uses a distinct synthetic campus/account; all writes roll back.
begin;
select set_config('request.jwt.claims','{"role":"service_role"}',true);
create temporary table marketplace_proof_results(check_name text) on commit drop;
do $$
declare
 c uuid:=gen_random_uuid(); c2 uuid:=gen_random_uuid(); buyer uuid:=gen_random_uuid(); admin uuid:=gen_random_uuid(); outsider uuid:=gen_random_uuid();
 listing uuid:=gen_random_uuid(); item uuid:=gen_random_uuid(); purchase uuid:=gen_random_uuid(); p2 uuid:=gen_random_uuid(); p3 uuid:=gen_random_uuid();
 oldcode uuid:=gen_random_uuid(); newcode uuid:=gen_random_uuid(); report uuid:=gen_random_uuid(); r2 uuid:=gen_random_uuid();
 hp_spend uuid; result jsonb; baseline_balance numeric; amount integer; n integer;
begin
 insert into campuses(id,name,slug,is_active,is_default) values(c,'audit_b_20261020_sql_'||c,c::text,true,false),(c2,'audit_b_20261020_sql_'||c2,c2::text,true,false);
 insert into auth.users(id,email,raw_user_meta_data) values
 (buyer,'audit_b_20261020_'||buyer||'@example.invalid','{}'),(admin,'audit_b_20261020_'||admin||'@example.invalid','{}'),(outsider,'audit_b_20261020_'||outsider||'@example.invalid','{}');
 insert into profiles(id,email,campus_id,role,is_active) values
 (buyer,'audit_b_20261020_'||buyer||'@example.invalid',c,'student',true),(admin,'audit_b_20261020_'||admin||'@example.invalid',c,'admin',true),(outsider,'audit_b_20261020_'||outsider||'@example.invalid',c2,'admin',true)
 on conflict(id) do update set campus_id=excluded.campus_id,role=excluded.role,is_active=true;
 insert into marketplace_listings(id,title,slug,vendor_name,listing_type,status,campus_id) values
 (listing,'audit_b_20261020_Code',listing::text,'Holy Grills','subscription','active',c),
 (item,'audit_b_20261020_Item',item::text,'Holy Grills','manual','active',c);
 insert into marketplace_purchases(id,user_id,listing_id,status,campus_id,is_fulfilled,metadata) values(purchase,buyer,listing,'completed',c,true,jsonb_build_object('answers',jsonb_build_object('meal','rice'),'code_id',oldcode,'code','old-owned-code'));
 insert into marketplace_access_codes(id,listing_id,code,status,assigned_purchase_id,campus_id) values(oldcode,listing,'old-owned-code','assigned',purchase,c),(newcode,listing,'replacement-owned-code','available',null,c);
 insert into marketplace_purchase_reports(id,purchase_id,user_id,campus_id,reason) values(report,purchase,buyer,c,'Owned broken code report');
 begin
  perform hg_admin_marketplace_resolve(purchase,outsider,'replace',report,null);
  raise exception 'Foreign admin was allowed';
 exception when insufficient_privilege then null; end;
 insert into marketplace_proof_results values('foreign campus admin denied');
 begin
  perform hg_admin_marketplace_resolve(purchase,buyer,'replace',report,null);
  raise exception 'Student was allowed';
 exception when insufficient_privilege then null; end;
 insert into marketplace_proof_results values('student actor denied');
 result:=hg_admin_marketplace_resolve(purchase,admin,'replace',report,'Owned resolution');
 assert result->>'status'='replaced' and not (result->>'replayed')::boolean;
 assert (select status from marketplace_access_codes where id=oldcode)='revoked';
 assert (select assigned_purchase_id from marketplace_access_codes where id=newcode)=purchase;
 assert (select metadata#>>'{answers,meal}' from marketplace_purchases where id=purchase)='rice';
 assert (select is_out_of_stock from marketplace_listings where id=listing);
 insert into marketplace_proof_results values('replacement atomically revokes old and assigns one new code; preserves answers; sold-out reflected');
 result:=hg_admin_marketplace_resolve(purchase,admin,'replace',report,'Owned resolution');
 assert (result->>'replayed')::boolean;
 assert (select count(*) from admin_audit_logs where entity_id=report::text)=1;
 insert into marketplace_proof_results values('closed action replay has one audit and no new assignment');
 begin
  perform hg_admin_marketplace_resolve(purchase,admin,'reject',report,null);
  raise exception 'Conflicting action was allowed';
 exception when sqlstate 'PT409' then null; end;
 insert into marketplace_proof_results values('conflicting final report action denied');
 insert into marketplace_purchase_reports(id,purchase_id,user_id,campus_id,reason) values(r2,purchase,buyer,c,'Owned replacement also broken');
 begin
  perform hg_admin_marketplace_resolve(purchase,admin,'replace',r2,null);
  raise exception 'Expected sold-out rejection';
 exception when raise_exception then
  if sqlerrm<>'marketplace_no_codes' then raise; end if;
 end;
 assert (select status from marketplace_purchase_reports where id=r2)='open';
 assert (select status from marketplace_access_codes where id=newcode)='assigned';
 insert into marketplace_proof_results values('sold-out replacement preserves original assignment and open report');
 -- Existing wallet policy: cash/card refunds both return to the wallet.
 insert into marketplace_purchases(id,user_id,listing_id,status,campus_id,quantity,wallet_amount,card_amount) values(p2,buyer,item,'pending',c,2,100,50);
 update marketplace_listings set inventory_count=0,status='paused' where id=item;
 insert into marketplace_listing_availability(listing_id,campus_id,inventory_count,is_out_of_stock) values(item,c,0,true);
 select coalesce((select balance from wallets where user_id=buyer),0) into baseline_balance;
 result:=hg_admin_marketplace_resolve(p2,admin,'refunded',null,null);
 assert result->>'status'='refunded';
 assert (select balance from wallets where user_id=buyer)=baseline_balance+150;
 assert (select inventory_count from marketplace_listings where id=item)=2;
 assert (select inventory_count from marketplace_listing_availability where listing_id=item and campus_id=c)=2;
 result:=hg_admin_marketplace_resolve(p2,admin,'refunded',null,null);
 assert (result->>'replayed')::boolean;
 assert (select inventory_count from marketplace_listings where id=item)=2;
 assert (select count(*) from wallet_transactions where reference_id=p2 and type='credit')=2;
 insert into marketplace_proof_results values('cash plus card wallet refund and stock restoration once; replay conserved');
 -- Failure after all financial writes simulates an interrupted enclosing transaction.
 insert into marketplace_purchases(id,user_id,listing_id,status,campus_id,quantity,wallet_amount) values(p3,buyer,item,'pending',c,1,75);
 select balance into baseline_balance from wallets where user_id=buyer;
 begin
  perform hg_admin_marketplace_resolve(p3,admin,'cancelled',null,null);
  raise exception 'owned synthetic post-write outage';
 exception when raise_exception then
  if sqlerrm<>'owned synthetic post-write outage' then raise; end if;
 end;
 assert (select status from marketplace_purchases where id=p3)='pending';
 assert (select balance from wallets where user_id=buyer)=baseline_balance;
 assert not exists(select 1 from wallet_transactions where reference_id=p3);
 assert (select inventory_count from marketplace_listings where id=item)=2;
 insert into marketplace_proof_results values('post-write failure rolls back refund/status/stock/audit together');
 -- A delivered code refund does not return a defective code to stock.
 select balance into baseline_balance from wallets where user_id=buyer;
 result:=hg_admin_marketplace_resolve(purchase,admin,'refund',r2,null);
 assert result->>'status'='refunded';
 assert (select status from marketplace_access_codes where id=newcode)='revoked';
 assert (select balance from wallets where user_id=buyer)=baseline_balance;
 assert (select metadata->'refund_receipt'->>'restocked' from marketplace_purchases where id=purchase)='false';
 insert into marketplace_proof_results values('report refund retires defective code without stock return');
 -- Restore the exact recorded HP debit, never today's listing HP price.
 p3:=gen_random_uuid();
 perform hg_add_hp_transaction(buyer,'earn',1000,'audit_owned_seed',null,null,null,'{}',null,c);
 hp_spend:=hg_add_hp_transaction(buyer,'spend',120,'marketplace_purchase','marketplace_spend',p3,null,'{}',null,c);
 insert into marketplace_purchases(id,user_id,listing_id,status,campus_id,quantity,pay_with_hp,hp_tx_id) values(p3,buyer,item,'pending',c,1,true,hp_spend);
 select hp_balance into amount from profiles where id=buyer;
 result:=hg_admin_marketplace_resolve(p3,admin,'cancelled',null,null);
 assert (select hp_balance from profiles where id=buyer)=amount+120;
 assert (select t.amount from hp_transactions t where t.reference_id=p3 and t.reference_type='marketplace_refund')=120;
 assert (select t.remaining_amount from hp_transactions t where t.reference_id=p3 and t.reference_type='marketplace_refund')=120;
 result:=hg_admin_marketplace_resolve(p3,admin,'cancelled',null,null);
 assert (result->>'replayed')::boolean;
 assert (select hp_balance from profiles where id=buyer)=amount+120;
 insert into marketplace_proof_results values('exact spent HP restored once without multiplier or mutable listing price');
 -- A stale completion cannot reopen a financially final purchase.
 begin
  perform hg_admin_marketplace_resolve(p3,admin,'completed',null,null);
  raise exception 'Reopened refunded purchase';
 exception when sqlstate 'PT409' then null; end;
 insert into marketplace_proof_results values('stale completion cannot reopen cancelled purchase');
 -- Completing a pending manual purchase persists fulfillment in the same lock boundary.
 p3:=gen_random_uuid();
 insert into marketplace_purchases(id,user_id,listing_id,status,campus_id,quantity) values(p3,buyer,item,'pending',c,1);
 result:=hg_admin_marketplace_resolve(p3,admin,'completed',null,null);
 assert (select is_fulfilled from marketplace_purchases where id=p3);
 begin
  perform hg_admin_marketplace_resolve(p3,admin,'pending',null,null);
  raise exception 'Reverted completed purchase';
 exception when sqlstate 'PT409' then null; end;
 insert into marketplace_proof_results values('manual completion persisted; backward pending transition rejected');
 -- Non-code completed purchase reports retain the reject action.
 r2:=gen_random_uuid();
 insert into marketplace_purchase_reports(id,purchase_id,user_id,campus_id,reason) values(r2,p3,buyer,c,'Owned manual purchase problem');
 result:=hg_admin_marketplace_resolve(p3,admin,'reject',r2,null);
 assert result->>'status'='rejected';
 insert into marketplace_proof_results values('manual purchase problem can be rejected without allocating code');
 assert not has_table_privilege('authenticated','public.marketplace_purchases','insert');
 assert not has_table_privilege('authenticated','public.marketplace_purchases','update');
 assert not has_table_privilege('authenticated','public.marketplace_purchase_reports','update');
 assert has_table_privilege('authenticated','public.marketplace_purchase_reports','insert');
 insert into marketplace_proof_results values('financial mutations restricted; customer report submission grant retained');
 assert not has_function_privilege('anon','public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text)','execute');
 assert not has_function_privilege('authenticated','public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text)','execute');
 assert has_function_privilege('service_role','public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text)','execute');
 insert into marketplace_proof_results values('only service role can execute new invoker transaction');
end;
$$;
select jsonb_agg(check_name) as passed from marketplace_proof_results;

rollback;
