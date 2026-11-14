-- Correct the dispatch diagnostic field to the existing schema column.
DO $$DECLARE definition text;BEGIN
 definition:=pg_get_functiondef('public.hg_begin_notification_dispatch(uuid,uuid,jsonb)'::regprocedure);
 IF position('last_error=''notice_no_longer_current''' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected dispatch guard';END IF;
 EXECUTE replace(definition,'last_error=''notice_no_longer_current''','error_message=''notice_no_longer_current''');
END$$;
