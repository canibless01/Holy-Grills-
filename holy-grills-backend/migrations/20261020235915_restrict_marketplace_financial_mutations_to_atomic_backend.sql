-- DEPLOYMENT GATE: apply after marketplace routes call hg_admin_marketplace_resolve.
-- Staff reads and authenticated customer report inserts remain available.
-- No browser role may forge purchase amounts or resolve reports outside the transaction.
drop policy if exists "marketplace_purchases: admins all" on public.marketplace_purchases;
drop policy if exists "marketplace_purchase_reports: admins all" on public.marketplace_purchase_reports;
create policy "marketplace_purchase_reports: admins read" on public.marketplace_purchase_reports
 for select to authenticated using (public.hg_is_campus_admin(campus_id));
drop policy if exists "marketplace_purchase_reports: users report own purchases" on public.marketplace_purchase_reports;
create policy "marketplace_purchase_reports: users report own purchases" on public.marketplace_purchase_reports
 for insert to authenticated with check (
  user_id=(select auth.uid()) and status='open'
  and exists(select 1 from public.marketplace_purchases p where p.id=purchase_id
   and p.user_id=(select auth.uid()) and p.status='completed' and p.campus_id is not distinct from marketplace_purchase_reports.campus_id)
 );
revoke insert,update,delete on public.marketplace_purchases from public,anon,authenticated;
revoke update,delete on public.marketplace_purchase_reports from public,anon,authenticated;
revoke insert on public.marketplace_purchase_reports from public,anon;
grant insert on public.marketplace_purchase_reports to authenticated;
grant select,insert,update,delete on public.marketplace_purchases,public.marketplace_purchase_reports to service_role;
-- A general completed-purchase problem can be rejected; only replacement needs a code listing.
do $$
declare definition text; original text; replacement text;
begin
 select pg_get_functiondef('public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text)'::regprocedure) into definition;
 original:=$old$if v_listing.listing_type not in ('code','digital_code','voucher','subscription') or v_purchase.status<>'completed' then$old$;
 replacement:=$new$if v_purchase.status<>'completed' or (p_action='replace' and v_listing.listing_type not in ('code','digital_code','voucher','subscription')) then$new$;
 if position(original in definition)=0 then raise exception 'Marketplace resolution prerequisite differs'; end if;
 execute replace(definition,original,replacement);
end;
$$;
