-- Queue one net actual-balance notice per account/asset/database transaction.
-- Deferred capture sees the final balance, so rollback/replay and intermediate
-- spend/restore writes cannot publish phantom changes. No historical backfill.
CREATE FUNCTION hg_internal.save_balance_activity(p_user uuid,p_asset text,p_ref uuid,p_delta numeric,p_pending boolean DEFAULT false,p_sources jsonb DEFAULT '[]',p_refs jsonb DEFAULT '[]') RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE person public.profiles%rowtype;prefs public.notification_preferences%rowtype;ch text;notice uuid;body text;title text;meta jsonb;kind text;amount text;
BEGIN
 IF p_delta=0 OR p_delta IS NULL THEN RETURN;END IF;
 SELECT * INTO person FROM public.profiles WHERE id=p_user AND is_active;
 IF NOT FOUND THEN RETURN;END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=p_user;
 IF p_asset='hp' AND prefs.hp_updates IS FALSE THEN RETURN;END IF;
 -- A specialised durable reward receipt in this transaction already explains
 -- the same HP change. Wallet transfers have their own recoverable receipts.
 IF p_asset='hp' AND EXISTS(SELECT 1 FROM public.notifications WHERE user_id=p_user AND created_at=transaction_timestamp() AND type IN
 ('milestone_achieved','ambassador_grant_issued','birthday_bonus','membership_anniversary','squad_hp_share','hp_transfer_recipient','checkin_streak_week','exclusive_spin_won')) THEN RETURN;END IF;
 IF p_asset='wallet' AND EXISTS(SELECT 1 FROM hg_internal.wallet_transfers WHERE p_user IN(sender_id,recipient_id) AND created_at=transaction_timestamp()) THEN RETURN;END IF;
 kind:=CASE WHEN p_asset='hp' THEN 'hp_balance_changed' ELSE 'wallet_balance_changed' END;
 title:=CASE WHEN p_asset='hp' THEN 'Your Holy Points, updated' ELSE 'Your wallet, updated' END;
 amount:=CASE WHEN p_asset='hp' THEN abs(p_delta)::bigint::text||' HP' ELSE '₦'||to_char(abs(p_delta),'FM999999999990.00') END;
 IF p_pending THEN body:=amount||' added to pending. Your next qualifying food order can unlock it.';
 ELSIF p_asset='hp' AND p_delta>0 AND p_sources ? 'referral' THEN
  title:='Your referral reward is in';body:=amount||' added to your active balance. Good food travels with good people.';
 ELSIF p_asset='hp' AND p_delta>0 AND p_sources ? 'food_order' THEN
  title:='Your plate brought rewards';body:=amount||' added to your active balance. Thanks for bringing your appetite.';
 ELSE body:=amount||CASE WHEN p_delta>0 THEN ' added to your ' ELSE ' deducted from your ' END||CASE WHEN p_asset='hp' THEN 'active HP balance.' ELSE 'wallet balance.' END;END IF;
 meta:=jsonb_build_object('_dispatch_version',1,'reference_type','balance_activity','reference_id',p_ref,'asset',p_asset,'delta',p_delta,'pending',p_pending,'sources',p_sources,'transaction_reference_ids',p_refs);
 FOREACH ch IN ARRAY ARRAY['in_app','push'] LOOP
  IF ch='push' AND (person.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
  notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:balance:'||p_user||':'||p_ref||':'||ch);
  INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,p_user,kind,title,body,ch,'/wallet',person.campus_id,p_ref,meta) ON CONFLICT(id) DO NOTHING;
 END LOOP;
END$$;
CREATE FUNCTION hg_internal.capture_balance_activity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE uid uuid;asset text;before_value numeric;after_value numeric;ref uuid;guc text;sources jsonb;refs jsonb;
BEGIN
 IF TG_TABLE_NAME='profiles' THEN
  uid:=NEW.id;asset:='hp';before_value:=OLD.hp_balance;
  SELECT hp_balance INTO after_value FROM public.profiles WHERE id=uid;
 ELSE
  uid:=NEW.user_id;asset:='wallet';before_value:=CASE WHEN TG_OP='INSERT' THEN 0 ELSE OLD.balance END;
  SELECT balance INTO after_value FROM public.wallets WHERE user_id=uid;
 END IF;
 guc:='hg.balance_'||md5(uid::text||asset);
 IF current_setting(guc,true)=pg_current_xact_id()::text THEN RETURN NEW;END IF;
 PERFORM set_config(guc,pg_current_xact_id()::text,true);
 IF after_value IS NULL OR coalesce(after_value,0)=coalesce(before_value,0) THEN RETURN NEW;END IF;
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:balance-transaction:'||pg_current_xact_id()||':'||uid||':'||asset);
 IF asset='hp' THEN
  SELECT coalesce(jsonb_agg(DISTINCT source) FILTER(WHERE source IS NOT NULL),'[]'),coalesce(jsonb_agg(DISTINCT reference_id) FILTER(WHERE reference_id IS NOT NULL),'[]') INTO sources,refs FROM public.hp_transactions WHERE user_id=uid AND created_at=transaction_timestamp();
 ELSE
  SELECT coalesce(jsonb_agg(DISTINCT reference_type) FILTER(WHERE reference_type IS NOT NULL),'[]'),coalesce(jsonb_agg(DISTINCT reference_id) FILTER(WHERE reference_id IS NOT NULL),'[]') INTO sources,refs FROM public.wallet_transactions WHERE user_id=uid AND created_at=transaction_timestamp();
 END IF;
 PERFORM hg_internal.save_balance_activity(uid,asset,ref,after_value-coalesce(before_value,0),false,sources,refs);
 RETURN NEW;
END$$;
CREATE FUNCTION hg_internal.capture_pending_hp_activity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NEW.status='pending' AND NEW.type IN('earn','adjustment') THEN
  PERFORM hg_internal.save_balance_activity(NEW.user_id,'hp',NEW.id,NEW.amount,true,jsonb_build_array(NEW.source),CASE WHEN NEW.reference_id IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(NEW.reference_id) END);
 END IF;
 RETURN NEW;
END$$;
REVOKE ALL ON FUNCTION hg_internal.save_balance_activity(uuid,text,uuid,numeric,boolean,jsonb,jsonb),hg_internal.capture_balance_activity(),hg_internal.capture_pending_hp_activity() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION hg_internal.save_balance_activity(uuid,text,uuid,numeric,boolean,jsonb,jsonb),hg_internal.capture_balance_activity(),hg_internal.capture_pending_hp_activity() TO service_role;
CREATE CONSTRAINT TRIGGER capture_profile_hp_balance_notice AFTER UPDATE ON public.profiles DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN(OLD.hp_balance IS DISTINCT FROM NEW.hp_balance) EXECUTE FUNCTION hg_internal.capture_balance_activity();
CREATE CONSTRAINT TRIGGER capture_wallet_balance_notice AFTER UPDATE ON public.wallets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN(OLD.balance IS DISTINCT FROM NEW.balance) EXECUTE FUNCTION hg_internal.capture_balance_activity();
CREATE CONSTRAINT TRIGGER capture_initial_wallet_balance_notice AFTER INSERT ON public.wallets DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_balance_activity();
CREATE CONSTRAINT TRIGGER capture_pending_hp_notice AFTER INSERT ON public.hp_transactions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hg_internal.capture_pending_hp_activity();
