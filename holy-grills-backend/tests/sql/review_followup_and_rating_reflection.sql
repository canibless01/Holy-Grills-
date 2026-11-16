-- Fresh synthetic actors only; no provider calls and every fixture is rolled back.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $verify$
DECLARE ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();actor uuid:=gen_random_uuid();owner uuid:=gen_random_uuid();super_id uuid:=gen_random_uuid();cat uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();o1 uuid:=gen_random_uuid();o2 uuid:=gen_random_uuid();r1 uuid:=gen_random_uuid();r2 uuid:=gen_random_uuid();n integer;stats record;before_balance integer;
BEGIN
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Review A','audit-review-'||ca),(cb,'[AUDIT rollback] Review B','audit-review-'||cb);
 INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(actor,'audit-review-'||actor||'@example.invalid','{"full_name":"[AUDIT rollback] Review admin"}'),(owner,'audit-review-'||owner||'@example.invalid','{"full_name":"[AUDIT rollback] Review owner"}'),(super_id,'audit-review-'||super_id||'@example.invalid','{"full_name":"[AUDIT rollback] Review super"}');
 UPDATE public.profiles SET campus_id=ca,role='admin' WHERE id=actor;
 UPDATE public.profiles SET campus_id=ca,role='student' WHERE id=owner;
 UPDATE public.profiles SET campus_id=cb,role='super_admin' WHERE id=super_id;
 SELECT hp_balance INTO before_balance FROM public.profiles WHERE id=owner;
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(cat,'[AUDIT rollback] Reviews','audit-review-'||cat,ca);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,campus_id) VALUES(meal,cat,'[AUDIT rollback] Reviewed meal','audit-review-'||meal,100,ca);
 INSERT INTO public.orders(id,user_id,campus_id,status,payment_status,subtotal,total_amount) VALUES(o1,owner,ca,'delivered','paid',200,200),(o2,owner,ca,'delivered','paid',100,100);
 INSERT INTO public.order_items(order_id,menu_item_id,name_snapshot,price_snapshot,quantity,line_total) VALUES(o1,meal,'[AUDIT rollback] Item',100,1,100),(o1,meal,'[AUDIT rollback] Item',100,1,100),(o2,meal,'[AUDIT rollback] Item',100,1,100);
 INSERT INTO public.order_reviews(id,order_id,user_id,rating,comment,hp_awarded,campus_id) VALUES(r1,o1,owner,1,'[AUDIT rollback] First',0,ca),(r2,o2,owner,5,'[AUDIT rollback] Second',0,ca);
 SELECT * INTO stats FROM public.get_menu_item_review_stats(ARRAY[meal]);
 IF stats.review_count<>2 OR stats.avg_rating<>3 THEN RAISE EXCEPTION 'public rating duplicate weighting';END IF;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',owner)::text,true);PERFORM set_config('role','authenticated',true);
 BEGIN UPDATE public.order_reviews SET is_flagged=true WHERE id=r1;RAISE EXCEPTION 'owner can change staff flag';EXCEPTION WHEN insufficient_privilege THEN NULL;END;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.order_reviews SET is_flagged=true,updated_at=now() WHERE id=r1;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'campus admin flag failed';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 UPDATE public.profiles SET campus_id=cb WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.order_reviews SET is_flagged=false WHERE id=r1;GET DIAGNOSTICS n=ROW_COUNT;IF n<>0 THEN RAISE EXCEPTION 'foreign campus flag accepted';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',super_id)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.order_reviews SET is_flagged=false,updated_at=now() WHERE id=r1;GET DIAGNOSTICS n=ROW_COUNT;IF n<>1 THEN RAISE EXCEPTION 'super admin clear failed';END IF;
 SELECT * INTO stats FROM public.get_menu_item_review_stats(ARRAY[meal]);IF stats.review_count<>2 OR stats.avg_rating<>3 THEN RAISE EXCEPTION 'flag modified public scores';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF (SELECT hp_balance FROM public.profiles WHERE id=owner)<>before_balance OR EXISTS(SELECT 1 FROM public.order_reviews WHERE id IN(r1,r2) AND hp_awarded<>0) THEN RAISE EXCEPTION 'follow-up modified HP';END IF;
END $verify$;
ROLLBACK;
SELECT 'PASS: fresh rollback reviews; public average deduplicates repeated item lines; owner flag denied, own-campus flag and super clear work, foreign-campus update denied, scores and HP unchanged' AS evidence;
