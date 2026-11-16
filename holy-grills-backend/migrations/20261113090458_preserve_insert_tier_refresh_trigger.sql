-- Insert activity and update/delete reconciliation are distinct trigger events.
DO $$DECLARE definition text;needle text:='  -- Tier update is owned by hg_on_hp_transaction_reconcile.';BEGIN
 definition:=pg_get_functiondef('public.hg_on_hp_transaction_insert()'::regprocedure);
 IF position(needle IN definition)=0 THEN RAISE EXCEPTION 'Unexpected HP activity trigger';END IF;
 EXECUTE replace(definition,needle,'  PERFORM public.hg_set_profile_tier_from_balance(NEW.user_id);');
END$$;
