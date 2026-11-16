-- Business state conflicts are HTTP409, not a retryable serialization failure.
-- Preserve the existing definition, signature, invoker mode and grants.
do $$
declare definition text;
begin
 select pg_get_functiondef('public.hg_admin_marketplace_resolve(uuid,uuid,text,uuid,text)'::regprocedure) into definition;
 if position('marketplace_conflict' in definition)=0 then
  raise exception 'Marketplace resolution prerequisite is missing';
 end if;
 execute replace(definition, 'errcode=''40001''', 'errcode=''PT409''');
end;
$$;
