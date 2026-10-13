CREATE OR REPLACE FUNCTION public.hg_protect_order_columns()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
  staff_cols text[] := array['status','notes','updated_at','received_at','paid_at','preparing_at','ready_at','assigned_at','out_for_delivery_at','delivered_at','cancelled_at','refunded_at','delivery_attempted_at','unclaimed_at','batch_id'];
  owner_cols text[] := array['status','notes','updated_at','cancelled_at','batch_id'];
  owner_only boolean; allowed text[]; k text;
begin
  if auth.role() = 'service_role' then return new; end if;
  if new.status is distinct from old.status then
    if new.status::text in ('preparing','ready','assigned','out_for_delivery','delivered') and new.payment_status::text not in ('paid','partially_refunded') then
      raise exception 'payment_required_for_preparation' using errcode='42501';
    end if;
    if new.status::text in ('cancelled','refunded') then
      raise exception 'financial_exit_rpc_only' using errcode='42501';
    end if;
    if hg_current_user_role()::text='kitchen' and new.status::text not in ('preparing','ready') then
      raise exception 'kitchen_preparation_only' using errcode='42501';
    end if;
  end if;
  if hg_is_campus_admin(old.campus_id) then return new; end if;

  -- Signup auto-link: guest order (no owner) gets its owner, token cleared, nothing else changes.
  if coalesce(current_setting('hg.linking_guest_orders', true), '') = 'on'
     and old.user_id is null
     and new.user_id is not null
     and new.claim_token is null
     and (to_jsonb(new) - array['user_id','claim_token','updated_at']) = (to_jsonb(old) - array['user_id','claim_token','updated_at'])
  then
    return new;
  end if;

  owner_only := coalesce(hg_current_user_role()::text, '') not in ('kitchen','rider');
  allowed := case when owner_only then owner_cols else staff_cols end;
  for k in select jsonb_object_keys(to_jsonb(new)) loop
    if to_jsonb(new) -> k is distinct from to_jsonb(old) -> k and not (k = any(allowed)) then
      raise exception 'Column "%" cannot be modified directly - use the appropriate API endpoint', k using errcode = '42501';
    end if;
  end loop;
  if owner_only then
    if new.status is distinct from old.status and new.status::text <> 'cancelled' then
      raise exception 'Customers can only cancel an order' using errcode = '42501';
    end if;
    if new.batch_id is distinct from old.batch_id and new.batch_id is not null then
      raise exception 'Customers cannot assign an order to a batch' using errcode = '42501';
    end if;
  end if;
  return new;
end $function$
