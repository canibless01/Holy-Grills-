-- Domain transaction only. Existing wallet/HP primitives are unchanged.
create or replace function public.hg_admin_marketplace_resolve(
 p_purchase_id uuid, p_actor_id uuid, p_action text,
 p_report_id uuid default null, p_admin_note text default null
) returns jsonb language plpgsql security invoker set search_path=public as $$
declare
 v_actor profiles%rowtype; v_purchase marketplace_purchases%rowtype;
 v_listing marketplace_listings%rowtype; v_report marketplace_purchase_reports%rowtype;
 v_code marketplace_access_codes%rowtype; v_old_code uuid;
 v_target text; v_report_target text; v_hp integer := 0; v_result jsonb;
begin
 if p_action is null or (p_report_id is null and p_action not in ('pending','completed','refunded','cancelled'))
    or (p_report_id is not null and p_action not in ('replace','refund','reject'))
    or length(coalesce(p_admin_note,''))>1000 then
  raise exception 'marketplace_invalid' using errcode='22023';
 end if;
 select * into v_actor from profiles where id=p_actor_id;
 if not found or not coalesce(v_actor.is_active,false) or v_actor.role not in ('admin','super_admin') then
  raise exception 'marketplace_forbidden' using errcode='42501';
 end if;
 select * into v_purchase from marketplace_purchases where id=p_purchase_id;
 if not found then raise exception 'marketplace_not_found' using errcode='P0002'; end if;
 if v_actor.role<>'super_admin' and (v_actor.campus_id is null or v_purchase.campus_id is distinct from v_actor.campus_id) then
  raise exception 'marketplace_forbidden' using errcode='42501';
 end if;
 -- Match admission lock ordering: buyer profile -> listing -> existing purchase.
 perform 1 from profiles where id=v_purchase.user_id for update;
 select * into v_listing from marketplace_listings where id=v_purchase.listing_id for update;
 select * into v_purchase from marketplace_purchases where id=p_purchase_id for update;
 if v_actor.role<>'super_admin' and (v_purchase.campus_id is distinct from v_actor.campus_id or
   (v_listing.campus_id is not null and v_listing.campus_id is distinct from v_actor.campus_id)) then
  raise exception 'marketplace_forbidden' using errcode='42501';
 end if;
 if p_report_id is not null then
  select * into v_report from marketplace_purchase_reports where id=p_report_id for update;
  if not found or v_report.purchase_id<>p_purchase_id or v_report.user_id<>v_purchase.user_id then
   raise exception 'marketplace_not_found' using errcode='P0002';
  end if;
  if v_report.campus_id is distinct from v_purchase.campus_id then
   raise exception 'marketplace_forbidden' using errcode='42501';
  end if;
  v_report_target:=case p_action when 'replace' then 'replaced' when 'refund' then 'refunded' else 'rejected' end;
  if v_report.status<> 'open' then
   if v_report.status=v_report_target then
    return jsonb_build_object('status',v_report.status,'purchase_id',p_purchase_id,'replayed',true);
   end if;
   raise exception 'marketplace_conflict' using errcode='40001';
  end if;
 end if;
 if p_report_id is null and v_purchase.status=p_action then
  return jsonb_build_object('status',v_purchase.status,'purchase_id',p_purchase_id,'replayed',true);
 end if;
 if v_purchase.status in ('refunded','cancelled') or (p_report_id is null and p_action='pending') then
  raise exception 'marketplace_conflict' using errcode='40001';
 end if;
 if p_report_id is null and p_action='completed' then
  if not v_purchase.is_fulfilled and v_listing.listing_type in ('code','digital_code','voucher','subscription') then
   select * into v_code from marketplace_access_codes where listing_id=v_listing.id and status='available'
     order by created_at,id limit 1 for update skip locked;
   if not found then raise exception 'marketplace_no_codes' using errcode='P0001'; end if;
   update marketplace_access_codes set status='assigned',assigned_purchase_id=p_purchase_id,assigned_at=now() where id=v_code.id;
   update marketplace_purchases set metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object('code',v_code.code,'code_id',v_code.id) where id=p_purchase_id;
   update marketplace_listings set is_out_of_stock=not exists(select 1 from marketplace_access_codes where listing_id=v_listing.id and status='available') where id=v_listing.id;
  end if;
  update marketplace_purchases set status='completed',is_fulfilled=true,fulfilled_at=coalesce(fulfilled_at,now()) where id=p_purchase_id;
  v_target:='completed';
 elsif p_report_id is not null and p_action in ('replace','reject') then
  if v_listing.listing_type not in ('code','digital_code','voucher','subscription') or v_purchase.status<>'completed' then
   raise exception 'marketplace_conflict' using errcode='40001';
  end if;
  if p_action='replace' then
   select * into v_code from marketplace_access_codes where listing_id=v_listing.id and status='available'
     order by created_at,id limit 1 for update skip locked;
   if not found then raise exception 'marketplace_no_codes' using errcode='P0001'; end if;
   v_old_code:=nullif(v_purchase.metadata->>'code_id','')::uuid;
   -- Never revoke a code belonging to another purchase, even if metadata is stale.
   if v_old_code is not null and not exists(select 1 from marketplace_access_codes
      where id=v_old_code and listing_id=v_listing.id and assigned_purchase_id=p_purchase_id and status='assigned') then
    raise exception 'marketplace_conflict' using errcode='40001';
   end if;
   update marketplace_access_codes set status='assigned',assigned_purchase_id=p_purchase_id,assigned_at=now() where id=v_code.id;
   update marketplace_access_codes set status='revoked',assigned_purchase_id=null where id=v_old_code and assigned_purchase_id=p_purchase_id;
   update marketplace_purchases set metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
     'code',v_code.code,'code_id',v_code.id,'replaced_code_id',v_old_code) where id=p_purchase_id;
   update marketplace_listings set is_out_of_stock=not exists(select 1 from marketplace_access_codes
     where listing_id=v_listing.id and status='available') where id=v_listing.id;
  end if;
 else
  -- A code delivery can be refunded only through an owned open report.
  if p_report_id is null and exists(select 1 from marketplace_access_codes where assigned_purchase_id=p_purchase_id and status='assigned') then
   raise exception 'marketplace_code_delivered' using errcode='P0001';
  end if;
  -- Earlier Python sagas have no atomic stock receipt. Do not guess how far a
  -- historical partial refund/reversal progressed or repay it a second time.
  if exists(select 1 from wallet_transactions where user_id=v_purchase.user_id and reference_id=p_purchase_id
      and reference_type in ('marketplace_refund','marketplace_refund_card','marketplace_refund_reversal'))
    or exists(select 1 from hp_transactions where user_id=v_purchase.user_id and reference_id=p_purchase_id and reference_type='marketplace_refund') then
   raise exception 'marketplace_legacy_refund_review' using errcode='P0001';
  end if;
  if v_purchase.pay_with_hp then
   select amount into v_hp from hp_transactions where id=v_purchase.hp_tx_id
    and user_id=v_purchase.user_id and type='spend' and reference_id=p_purchase_id;
   if v_hp is null or v_hp<=0 then raise exception 'marketplace_legacy_refund_review' using errcode='P0001'; end if;
  end if;
  if v_purchase.wallet_amount>0 then
   v_result:=public.credit_wallet_atomic(p_user_id=>v_purchase.user_id,p_amount=>v_purchase.wallet_amount,
    p_reason=>'Marketplace refund',p_reference_type=>'marketplace_refund',p_reference_id=>p_purchase_id,
    p_provider=>'paystack',p_provider_reference=>'REFUND-MKT-'||p_purchase_id::text,
    p_metadata=>'{}'::jsonb,p_campus_id=>v_purchase.campus_id);
   if v_result ? 'error' then raise exception 'marketplace_refund_failed'; end if;
  end if;
  if v_hp>0 then
   v_result:=public.record_hp_transaction_atomic(p_user_id=>v_purchase.user_id,p_amount=>v_hp,p_type=>'earn',
    p_status=>'active',p_source=>'marketplace',p_reference_type=>'marketplace_refund',p_reference_id=>p_purchase_id,
    p_issued_by_admin_id=>null,p_notes=>'Marketplace HP refund',p_campus_id=>v_purchase.campus_id);
   if v_result ? 'error' then raise exception 'marketplace_refund_failed'; end if;
   perform public.hg_set_profile_tier_from_balance(v_purchase.user_id);
  end if;
  if v_purchase.card_amount>0 then
   v_result:=public.credit_wallet_atomic(p_user_id=>v_purchase.user_id,p_amount=>v_purchase.card_amount,
    p_reason=>'Marketplace card portion refunded to wallet',p_reference_type=>'marketplace_refund_card',p_reference_id=>p_purchase_id,
    p_provider=>'paystack',p_provider_reference=>'REFUND-MKT-CARD-'||p_purchase_id::text,
    p_metadata=>'{}'::jsonb,p_campus_id=>v_purchase.campus_id);
   if v_result ? 'error' then raise exception 'marketplace_refund_failed'; end if;
  end if;
  if p_report_id is null then
   update marketplace_listings set inventory_count=inventory_count+v_purchase.quantity,
    is_out_of_stock=false,status=case when inventory_count<=0 and status='paused' then 'active' else status end
    where id=v_listing.id and inventory_count is not null;
   update marketplace_listing_availability set inventory_count=inventory_count+v_purchase.quantity,
    is_out_of_stock=false,updated_at=now() where listing_id=v_listing.id and campus_id=v_purchase.campus_id and inventory_count is not null;
  end if;
  -- Defective/reported codes are retired, never returned to the sale pool.
  update marketplace_access_codes set status='revoked',assigned_purchase_id=null
   where assigned_purchase_id=p_purchase_id;
  v_target:=case when p_report_id is not null then 'refunded' else p_action end;
  update marketplace_purchases set status=v_target,metadata=coalesce(metadata,'{}'::jsonb)||jsonb_build_object(
    'refund_receipt',jsonb_build_object('version',1,'at',now(),'restocked',p_report_id is null,'actor_id',p_actor_id))
    where id=p_purchase_id;
 end if;
 if p_report_id is not null then
  update marketplace_purchase_reports set status=v_report_target,admin_note=nullif(p_admin_note,''),
    resolved_by=p_actor_id,resolved_at=now(),updated_at=now() where id=p_report_id;
 else
  update marketplace_purchases set admin_note=coalesce(nullif(p_admin_note,''),admin_note) where id=p_purchase_id;
 end if;
 insert into admin_audit_logs(actor_id,actor_role,entity_type,entity_id,action,before_value,after_value,campus_id)
  values(p_actor_id,v_actor.role,case when p_report_id is null then 'marketplace_purchase' else 'marketplace_report' end,
   coalesce(p_report_id,p_purchase_id)::text,p_action,jsonb_build_object('purchase_status',v_purchase.status),
   jsonb_build_object('status',coalesce(v_report_target,v_target),'purchase_id',p_purchase_id),v_purchase.campus_id);
 return jsonb_build_object('status',coalesce(v_report_target,v_target),'purchase_id',p_purchase_id,
   'code',v_code.code,'replayed',false);
end;
$$;
revoke all on function public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text) from public,anon,authenticated;
grant execute on function public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text) to service_role;
