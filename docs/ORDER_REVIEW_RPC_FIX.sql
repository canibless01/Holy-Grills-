-- Review creation, its real pending HP award and monthly allowance are committed
-- together using existing tables and the existing HP transaction function.
CREATE OR REPLACE FUNCTION public.hg_submit_order_review_atomic(
 p_user_id uuid,p_order_id uuid,p_rating integer,p_kitchen_rating integer,
 p_rider_rating integer,p_comment text,p_hp_amount integer,p_monthly_cap integer,
 p_image_urls text[] DEFAULT '{}'::text[]
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public
AS $review$
DECLARE
 o public.orders%ROWTYPE;
 r public.order_reviews%ROWTYPE;
 v_month text := to_char(now() AT TIME ZONE 'UTC','YYYY-MM');
 v_earned integer;
 v_award integer;
 v_hp jsonb;
BEGIN
 IF coalesce(auth.role(),'')<>'service_role' THEN
  RETURN jsonb_build_object('success',false,'error','forbidden');
 END IF;
 IF p_rating IS NULL OR p_rating NOT BETWEEN 1 AND 5
    OR (p_kitchen_rating IS NOT NULL AND p_kitchen_rating NOT BETWEEN 1 AND 5)
    OR (p_rider_rating IS NOT NULL AND p_rider_rating NOT BETWEEN 1 AND 5)
    OR p_hp_amount IS NULL OR p_hp_amount<0 OR p_monthly_cap IS NULL OR p_monthly_cap<0
    OR length(coalesce(p_comment,''))>2000 OR cardinality(coalesce(p_image_urls,'{}'::text[]))>3 THEN
  RETURN jsonb_build_object('success',false,'error','invalid_review');
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_user_id AND is_active) THEN
  RETURN jsonb_build_object('success',false,'error','forbidden');
 END IF;
 SELECT * INTO o FROM public.orders WHERE id=p_order_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','order_not_found'); END IF;
 IF o.user_id IS DISTINCT FROM p_user_id THEN
  RETURN jsonb_build_object('success',false,'error','forbidden');
 END IF;
 IF o.status::text<>'delivered' THEN
  RETURN jsonb_build_object('success',false,'error','not_delivered');
 END IF;
 SELECT * INTO r FROM public.order_reviews WHERE order_id=p_order_id AND user_id=p_user_id;
 IF FOUND THEN
  IF r.rating IS DISTINCT FROM p_rating OR r.kitchen_rating IS DISTINCT FROM p_kitchen_rating
     OR r.rider_rating IS DISTINCT FROM p_rider_rating OR coalesce(r.comment,'')<>coalesce(p_comment,'')
     OR coalesce(r.image_urls,'{}'::text[]) IS DISTINCT FROM coalesce(p_image_urls,'{}'::text[]) THEN
   RETURN jsonb_build_object('success',false,'error','already_reviewed');
  END IF;
  RETURN jsonb_build_object('success',true,'idempotent',true,'review',to_jsonb(r),'hp_awarded',r.hp_awarded);
 END IF;
 INSERT INTO public.monthly_hp_tracker(user_id,month,total_earned,campus_id)
 VALUES(p_user_id,v_month,0,o.campus_id) ON CONFLICT(user_id,month) DO NOTHING;
 SELECT total_earned INTO v_earned FROM public.monthly_hp_tracker
  WHERE user_id=p_user_id AND month=v_month FOR UPDATE;
 v_award := least(p_hp_amount,greatest(0,p_monthly_cap-coalesce(v_earned,0)));
 INSERT INTO public.order_reviews(order_id,user_id,rating,kitchen_rating,rider_rating,comment,
                                 hp_awarded,hp_rewarded,campus_id,image_urls)
 VALUES(p_order_id,p_user_id,p_rating,p_kitchen_rating,p_rider_rating,coalesce(p_comment,''),
        v_award,v_award,o.campus_id,coalesce(p_image_urls,'{}'::text[])) RETURNING * INTO r;
 IF v_award>0 THEN
  v_hp := public.record_hp_transaction_atomic(p_user_id,v_award,'earn','pending','review',
           'review',r.id,NULL,NULL,o.campus_id);
  IF NOT coalesce((v_hp->>'success')::boolean,false) OR v_hp ? 'error' THEN
   RAISE EXCEPTION 'review_hp_failed' USING ERRCODE='P0001';
  END IF;
  UPDATE public.monthly_hp_tracker SET total_earned=total_earned+v_award,updated_at=now()
   WHERE user_id=p_user_id AND month=v_month;
 END IF;
 RETURN jsonb_build_object('success',true,'idempotent',false,'review',to_jsonb(r),
                          'hp_awarded',v_award,'hp_capped',v_award<p_hp_amount);
EXCEPTION WHEN OTHERS THEN
 RETURN jsonb_build_object('success',false,'error','review_failed','debug_code',SQLSTATE);
END;
$review$;
REVOKE ALL ON FUNCTION public.hg_submit_order_review_atomic(uuid,uuid,integer,integer,integer,text,integer,integer,text[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_submit_order_review_atomic(uuid,uuid,integer,integer,integer,text,integer,integer,text[]) TO service_role;
