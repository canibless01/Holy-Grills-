BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
CREATE FUNCTION pg_temp.lookup_refusal(statement text, expected text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 BEGIN EXECUTE statement; EXCEPTION WHEN OTHERS THEN IF SQLERRM=expected THEN RETURN; END IF;RAISE;END;
 RAISE EXCEPTION 'Expected recipient refusal: %',expected;
END $$;
DO $test$
DECLARE c uuid:=gen_random_uuid(); other_c uuid:=gen_random_uuid();a uuid:=gen_random_uuid();b uuid:=gen_random_uuid();duplicate uuid:=gen_random_uuid();foreign_user uuid:=gen_random_uuid();u uuid;
 email text;foreign_email text; result jsonb; chosen jsonb; transfer_id uuid:=gen_random_uuid();
BEGIN
 INSERT INTO campuses(id,name,slug) VALUES(c,'[AUDIT rollback] Wallet lookup','audit-lookup-'||c),(other_c,'[AUDIT rollback] Foreign lookup','audit-lookup-'||other_c);
 FOREACH u IN ARRAY ARRAY[a,b,duplicate,foreign_user] LOOP
  INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(u,'audit-lookup-'||u||'@example.invalid','{"full_name":"[AUDIT rollback] Lookup member"}');
  UPDATE profiles SET is_active=true,campus_id=CASE WHEN id=foreign_user THEN other_c ELSE c END,email='audit-lookup-'||u||'@example.invalid',referral_code=upper(replace(u::text,'-','')) WHERE id=u;
 END LOOP;
 email:='audit-lookup-'||b||'@example.invalid';foreign_email:='audit-lookup-'||foreign_user||'@example.invalid';
 UPDATE profiles SET phone='+2348011223344' WHERE id=b;
 UPDATE profiles SET phone='+2348019999999' WHERE id=foreign_user;
 INSERT INTO feature_flags(feature_name,is_active,campus_id) VALUES('wallet_transfer',true,c);
 INSERT INTO system_settings(key,value,campus_id) VALUES('wallet_transfer_min_amount','1',c),('wallet_transfer_max_amount','100',c),('wallet_transfer_daily_limit','100',c);
 chosen:=hg_wallet_transfer('lookup',a,NULL,jsonb_build_object('lookup_type','email','value',upper(email)));
 IF chosen->>'id'<>b::text OR chosen ? 'email' OR chosen ? 'phone' OR chosen ? 'balance' THEN RAISE EXCEPTION 'Exact private email lookup failed';END IF;
 result:=hg_wallet_transfer('lookup',a,NULL,'{"lookup_type":"phone","value":"2348011223344"}');
 IF result->>'id'<>b::text OR result ? 'email' OR result ? 'phone' THEN RAISE EXCEPTION 'Exact private phone lookup failed';END IF;
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('lookup_type','email','value',foreign_email)),'recipient_unavailable');
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,''{"lookup_type":"phone","value":"2348019999999"}'')',a),'recipient_unavailable');
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('lookup_type','email','value','audit-lookup-'||a||'@example.invalid')),'self_transfer');
 UPDATE profiles SET is_active=false WHERE id=b;
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('lookup_type','email','value',email)),'recipient_unavailable');
 UPDATE profiles SET is_active=true WHERE id=b;
 -- Different stored phone formats for the same number must be ambiguous.
 UPDATE profiles SET phone='080 1122 3344' WHERE id=duplicate;
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,''{"lookup_type":"phone","value":"2348011223344"}'')',a),'recipient_ambiguous');
 -- Email still selects one account; no arbitrary first phone match is used.
 result:=hg_wallet_transfer('lookup',a,NULL,jsonb_build_object('lookup_type','email','value',email));
 IF result->>'id'<>b::text THEN RAISE EXCEPTION 'Unique email affected by duplicate phone';END IF;
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,''{"lookup_type":"name","value":"Lookup"}'')',a),'invalid_recipient_identifier');
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,''{"lookup_type":"email","value":"%%example.invalid"}'')',a),'invalid_recipient_identifier');
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,''{"lookup_type":"email","value":"member@example.invalid"}'')',a),'recipient_unavailable');
 INSERT INTO wallets(user_id,balance,currency,campus_id) VALUES(a,10,'NGN',c),(b,0,'NGN',c) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,currency='NGN';
 result:=hg_wallet_transfer('send',a,transfer_id,jsonb_build_object('recipient_id',chosen->>'id','recipient_code',chosen->>'code','amount_kobo',100));
 IF result->>'recipient_id'<>b::text OR (SELECT balance FROM wallets WHERE user_id=a)<>9 OR (SELECT balance FROM wallets WHERE user_id=b)<>1
 OR (SELECT count(*) FROM wallet_transactions WHERE reference_id=transfer_id)<>2 THEN RAISE EXCEPTION 'Lookup-selected identity did not use conserved transfer path';END IF;
 UPDATE feature_flags SET is_active=false WHERE campus_id=c AND feature_name='wallet_transfer';
 PERFORM pg_temp.lookup_refusal(format('SELECT hg_wallet_transfer(''lookup'',%L,NULL,%L)',a,jsonb_build_object('lookup_type','email','value',email)),'transfers_paused');
END $test$;
ROLLBACK;
