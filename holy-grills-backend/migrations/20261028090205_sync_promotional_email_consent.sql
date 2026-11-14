CREATE OR REPLACE FUNCTION public.hg_update_notification_preferences_atomic(p_user_id uuid, p_preferences jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE v_profile public.profiles%ROWTYPE; v_prefs public.notification_preferences%ROWTYPE;
BEGIN
 IF p_preferences IS NULL OR jsonb_typeof(p_preferences)<>'object' OR p_preferences='{}'::jsonb THEN RAISE EXCEPTION 'notification_preferences_invalid'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each(p_preferences) e WHERE e.key NOT IN ('push_enabled','email_enabled','order_updates','delivery_updates','hp_updates','promotions') OR jsonb_typeof(e.value)<>'boolean') THEN RAISE EXCEPTION 'notification_preferences_invalid'; END IF;
 SELECT * INTO v_profile FROM public.profiles WHERE id=p_user_id AND is_active FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'notification_user_inactive'; END IF;
 INSERT INTO public.notification_preferences(user_id,campus_id,push_enabled,email_enabled)
 VALUES(p_user_id,v_profile.campus_id,COALESCE(v_profile.push_enabled,true),COALESCE(v_profile.email_notifications,true)) ON CONFLICT(user_id) DO NOTHING;
 UPDATE public.notification_preferences SET
 push_enabled=COALESCE((p_preferences->>'push_enabled')::boolean,push_enabled),
 email_enabled=COALESCE((p_preferences->>'email_enabled')::boolean,email_enabled),
 order_updates=COALESCE((p_preferences->>'order_updates')::boolean,order_updates),
 delivery_updates=COALESCE((p_preferences->>'delivery_updates')::boolean,delivery_updates),
 hp_updates=COALESCE((p_preferences->>'hp_updates')::boolean,hp_updates),
 promotions=COALESCE((p_preferences->>'promotions')::boolean,promotions),
 campus_id=v_profile.campus_id,updated_at=now() WHERE user_id=p_user_id RETURNING * INTO v_prefs;
 IF p_preferences ? 'push_enabled' OR p_preferences ? 'email_enabled' THEN
 UPDATE public.profiles SET
 push_enabled=COALESCE((p_preferences->>'push_enabled')::boolean,push_enabled),
 email_notifications=COALESCE((p_preferences->>'email_enabled')::boolean,email_notifications),updated_at=now() WHERE id=p_user_id;
 END IF;
 IF p_preferences ? 'promotions' THEN
   IF (p_preferences->>'promotions')::boolean THEN
     INSERT INTO public.newsletter_subscriptions(email,full_name,campus_id,source,is_confirmed,unsubscribed_at)
     VALUES(lower(v_profile.email),v_profile.full_name,v_profile.campus_id,'preferences',true,null)
     ON CONFLICT(email) DO UPDATE SET unsubscribed_at=null,is_confirmed=true,campus_id=excluded.campus_id;
   ELSE
     UPDATE public.newsletter_subscriptions SET unsubscribed_at=coalesce(unsubscribed_at,now()) WHERE email=lower(v_profile.email);
   END IF;
 END IF;
 RETURN to_jsonb(v_prefs);
END;
$function$;
