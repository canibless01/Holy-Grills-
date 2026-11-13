-- One immutable membership award per account/milestone. No historical replay on rollout.
CREATE FUNCTION public.hg_award_membership_anniversary(p_user uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE recipient public.profiles%rowtype;prefs public.notification_preferences%rowtype;old_grant public.hp_transactions%rowtype;
 today date:=(now() AT TIME ZONE 'Africa/Lagos')::date;joined date;due date;months_member integer;hp integer;ref uuid;r jsonb;receipts integer;
 month_start timestamptz:=date_trunc('month',now() AT TIME ZONE 'Africa/Lagos') AT TIME ZONE 'Africa/Lagos';
 awarded integer:=0;channel_name text;notice uuid;title text;body text;meta jsonb;legacy boolean:=false;
BEGIN
 SELECT * INTO recipient FROM public.profiles WHERE id=p_user FOR UPDATE;
 IF recipient.id IS NULL OR recipient.is_active IS NOT TRUE OR recipient.role::text<>'student' OR coalesce(recipient.is_fraud_flagged,false)
 OR recipient.campus_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.campuses WHERE id=recipient.campus_id AND is_active) THEN RETURN jsonb_build_object('success',true,'awarded',0,'reason','excluded');END IF;
 joined:=(recipient.created_at AT TIME ZONE 'Africa/Lagos')::date;
 months_member:=(extract(year from today)::integer-extract(year from joined)::integer)*12+extract(month from today)::integer-extract(month from joined)::integer;
 due:=(joined+make_interval(months=>months_member))::date;
 IF months_member<=0 OR due>today THEN RETURN jsonb_build_object('success',true,'awarded',0,'reason','not_due');END IF;
 ref:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:membership-anniversary:'||recipient.id||':'||months_member);
 SELECT count(*) INTO receipts FROM public.hp_transactions WHERE user_id=p_user AND reference_type='membership_anniversary'
 AND (reference_id=ref OR (reference_id IS NULL AND created_at>=month_start));
 IF receipts>1 THEN RETURN jsonb_build_object('error','legacy_membership_review_required');END IF;
 IF receipts=1 THEN
  SELECT * INTO old_grant FROM public.hp_transactions WHERE user_id=p_user AND reference_type='membership_anniversary'
   AND (reference_id=ref OR (reference_id IS NULL AND created_at>=month_start));
  IF old_grant.type<>'earn' OR old_grant.status<>'active' OR old_grant.campus_id IS DISTINCT FROM recipient.campus_id
   OR old_grant.metadata->>'notes' IS DISTINCT FROM 'Membership anniversary — '||months_member||' months' THEN RETURN jsonb_build_object('error','legacy_membership_review_required');END IF;
  hp:=old_grant.amount;legacy:=old_grant.reference_id IS NULL;
 ELSE
  SELECT hp_awarded INTO hp FROM public.membership_rewards WHERE months=months_member AND is_active
   AND campus_id IS NOT DISTINCT FROM CASE WHEN EXISTS(SELECT 1 FROM public.membership_rewards WHERE campus_id=recipient.campus_id) THEN recipient.campus_id ELSE NULL::uuid END ORDER BY id LIMIT 1;
  IF hp IS NULL OR hp<=0 THEN RETURN jsonb_build_object('success',true,'awarded',0,'reason','no_reward');END IF;
  r:=public.record_hp_transaction_atomic(p_user,hp,'earn','active','membership_anniversary','membership_anniversary',ref,NULL,'Membership anniversary — '||months_member||' months',recipient.campus_id);
  IF r ? 'error' THEN RAISE EXCEPTION '%',r->>'error';END IF;
  IF NOT coalesce((r->>'replayed')::boolean,false) THEN
   awarded:=hp;
   PERFORM public.increment_monthly_hp_tracker(p_user,to_char(today,'YYYY-MM'),hp);
  END IF;
 END IF;
 SELECT * INTO prefs FROM public.notification_preferences WHERE user_id=p_user;
 IF prefs.hp_updates IS DISTINCT FROM false THEN
  title:='🎉 '||months_member||'-Month Anniversary!';
  body:='Happy '||months_member||'-month anniversary! You have earned '||hp||' HP as a thank-you.';
  meta:=jsonb_build_object('_dispatch_version',1,'reference_type','membership_anniversary','reference_id',ref,'months',months_member,'hp',hp);
  FOREACH channel_name IN ARRAY ARRAY['in_app','push'] LOOP
   IF channel_name='push' AND (recipient.push_enabled IS FALSE OR prefs.push_enabled IS FALSE) THEN CONTINUE;END IF;
   -- Old Python notices had random IDs; keep their already-recorded channels.
   IF legacy AND EXISTS(SELECT 1 FROM public.notifications WHERE user_id=p_user AND type='membership_anniversary' AND channel=channel_name AND created_at>=month_start) THEN CONTINUE;END IF;
   notice:=extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','holy-grills:membership-anniversary-notice:'||ref||':'||channel_name);
   INSERT INTO public.notifications(id,user_id,type,title,body,channel,action_url,campus_id,reference_id,metadata)
   VALUES(notice,p_user,'membership_anniversary',title,body,channel_name,'/wallet',recipient.campus_id,ref,meta) ON CONFLICT(id) DO NOTHING;
  END LOOP;
 END IF;
 RETURN jsonb_build_object('success',true,'awarded',awarded,'hp',hp,'months',months_member,'replayed',receipts=1,'reference_id',ref);
END$$;
REVOKE ALL ON FUNCTION public.hg_award_membership_anniversary(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_award_membership_anniversary(uuid) TO service_role;
