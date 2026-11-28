-- Bind only unowned invitations in the account's actual campus. No backfill at migration time.
CREATE FUNCTION public.hg_bind_squad_identity(p_user uuid) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE recipient public.profiles%rowtype;
BEGIN
 SELECT * INTO recipient FROM public.profiles WHERE id=p_user AND is_active AND campus_id IS NOT NULL;
 IF NOT FOUND THEN RETURN;END IF;
 UPDATE public.squad_roster r SET user_id=recipient.id FROM public.squads s
 WHERE r.squad_id=s.id AND s.campus_id=recipient.campus_id AND r.user_id IS NULL
 AND lower(trim(r.email))=lower(trim(recipient.email::text));
 UPDATE public.squad_members m SET user_id=recipient.id,is_registered=true FROM public.orders o
 WHERE m.order_id=o.id AND o.campus_id=recipient.campus_id AND m.campus_id=recipient.campus_id
 AND m.user_id IS NULL AND lower(trim(m.email))=lower(trim(recipient.email::text));
END$$;
REVOKE ALL ON FUNCTION public.hg_bind_squad_identity(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_bind_squad_identity(uuid) TO service_role;

CREATE FUNCTION public.hg_claim_pending_squad_hp(p_pending uuid,p_user uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE pending public.pending_squad_hp%rowtype;ord public.orders%rowtype;recipient public.profiles%rowtype;
 existing public.hp_transactions%rowtype;receipt_count integer;result jsonb;awarded integer:=0;
 prefs public.notification_preferences%rowtype;notice uuid;channel_name text;body text;meta jsonb;oid uuid;
BEGIN
 SELECT order_id INTO oid FROM public.pending_squad_hp WHERE id=p_pending;
 IF NOT FOUND THEN RETURN jsonb_build_object('error','pending_share_not_found');END IF;
 -- Match delivery's order-before-profile locking; one order per transaction.
 SELECT * INTO ord FROM public.orders WHERE id=oid FOR UPDATE;
 SELECT * INTO pending FROM public.pending_squad_hp WHERE id=p_pending FOR UPDATE;
 SELECT * INTO recipient FROM public.profiles WHERE id=p_user FOR UPDATE;
 IF recipient.id IS NULL OR recipient.is_active IS NOT TRUE OR recipient.campus_id IS NULL
 OR lower(trim(recipient.email::text)) IS DISTINCT FROM lower(trim(pending.email))
 OR pending.campus_id IS DISTINCT FROM recipient.campus_id OR ord.campus_id IS DISTINCT FROM recipient.campus_id
 OR ord.id IS NULL OR ord.user_id=recipient.id THEN RETURN jsonb_build_object('error','squad_recipient_unavailable');END IF;
 IF pending.status='claimed' THEN RETURN jsonb_build_object('success',true,'replayed',true,'awarded',0,'order_id',ord.id);END IF;
 IF pending.status<>'pending' OR pending.hp_amount IS NULL OR pending.hp_amount<=0
 OR ord.status::text<>'delivered' OR ord.payment_status::text NOT IN ('paid','partially_refunded')
 OR ord.is_squad_order IS NOT TRUE OR ord.squad_hp_distributed IS NOT TRUE THEN RETURN jsonb_build_object('error','delivered_squad_share_required');END IF;
 SELECT count(*) INTO receipt_count FROM public.hp_transactions WHERE user_id=recipient.id AND reference_id=ord.id
 AND reference_type IN ('squad_split','squad_split_claimed');
 IF receipt_count>1 THEN RETURN jsonb_build_object('error','legacy_squad_share_review_required');END IF;
 IF receipt_count=1 THEN
  SELECT * INTO existing FROM public.hp_transactions WHERE user_id=recipient.id AND reference_id=ord.id AND reference_type IN ('squad_split','squad_split_claimed');
  IF existing.amount<>pending.hp_amount OR existing.type<>'earn' OR existing.status<>'active' OR existing.campus_id IS DISTINCT FROM recipient.campus_id
  THEN RETURN jsonb_build_object('error','legacy_squad_share_review_required');END IF;
 ELSE
  result:=public.record_hp_transaction_atomic(recipient.id,pending.hp_amount,'earn','active','squad_split_claimed','squad_split_claimed',ord.id,NULL,'Squad HP claimed from order '||left(ord.id::text,8),recipient.campus_id);
  IF result ? 'error' THEN RAISE EXCEPTION '%',result->>'error';END IF;
  IF NOT coalesce((result->>'replayed')::boolean,false) THEN
   awarded:=pending.hp_amount;
   PERFORM public.increment_monthly_hp_tracker(recipient.id,to_char(now() AT TIME ZONE 'Africa/Lagos','YYYY-MM'),awarded);
  END IF;
 END IF;
 UPDATE public.pending_squad_hp SET status='claimed' WHERE id=pending.id;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=recipient.id;
 IF prefs.hp_updates IS DISTINCT FROM false THEN
  body:='You earned '||pending.hp_amount||' HP from your squad order.';
  FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
   IF channel_name='push' AND (recipient.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:squad-claim:'||ord.id||':'||recipient.id||':'||channel_name);
   meta:=jsonb_build_object('_dispatch_version',1,'reference_type','squad_split_claimed','reference_id',ord.id,'pending_share_id',pending.id);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,recipient.id,'squad_hp_share','Your squad HP share!',body,channel_name,'/wallet',recipient.campus_id,ord.id,meta) ON CONFLICT(id) DO NOTHING;
  END LOOP;
 END IF;
 RETURN jsonb_build_object('success',true,'replayed',receipt_count=1,'awarded',awarded,'order_id',ord.id);
END$$;
REVOKE ALL ON FUNCTION public.hg_claim_pending_squad_hp(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_claim_pending_squad_hp(uuid,uuid) TO service_role;
