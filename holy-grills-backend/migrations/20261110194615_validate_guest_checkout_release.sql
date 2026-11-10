DO $patch$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_abandon_checkout(uuid,uuid,text,text,text,text)'::regprocedure);
 IF position('OR saved.order_lock_id IS NOT NULL ' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected checkout release definition'; END IF;
 -- Order locks are stored in order_locks.used_order_id, not an orders column.
 -- Anonymous checkout cannot redeem an account-owned order lock.
 definition:=replace(definition,'OR saved.order_lock_id IS NOT NULL ','');
 EXECUTE definition;
END $patch$;
