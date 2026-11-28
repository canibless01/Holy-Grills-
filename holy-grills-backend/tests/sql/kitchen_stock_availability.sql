-- Kitchen availability toggle backing rows, actual role/campus policies; rollback only.
BEGIN;
SET LOCAL request.jwt.claims='{"role":"service_role"}';
DO $audit$
DECLARE actor uuid;ca uuid:=gen_random_uuid();cb uuid:=gen_random_uuid();category uuid:=gen_random_uuid();meal uuid:=gen_random_uuid();n integer;
BEGIN
 SELECT p.id INTO actor FROM public.profiles p LEFT JOIN public.campuses c ON c.id=p.campus_id WHERE p.full_name ILIKE '%audit%' AND coalesce(c.name,'') NOT LIKE '[AUDIT PROVIDER%' ORDER BY p.id LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'isolated audit profile required';END IF;
 INSERT INTO public.campuses(id,name,slug) VALUES(ca,'[AUDIT rollback] Stock A','audit-stock-'||ca),(cb,'[AUDIT rollback] Stock B','audit-stock-'||cb);
 UPDATE public.profiles SET role='kitchen',campus_id=ca,is_active=true WHERE id=actor;
 INSERT INTO public.menu_categories(id,name,slug,campus_id) VALUES(category,'[AUDIT rollback] Stock','audit-stock-'||category,null);
 INSERT INTO public.menu_items(id,category_id,name,slug,price,hp_earn_value,campus_id,is_available) VALUES(meal,category,'[AUDIT rollback] Meal','audit-stock-'||meal,100,10,null,true);
 INSERT INTO public.menu_item_availability(menu_item_id,campus_id,is_available) VALUES(meal,cb,true);
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 INSERT INTO public.menu_item_availability(menu_item_id,campus_id,is_available) VALUES(meal,ca,false) ON CONFLICT(menu_item_id,campus_id) DO UPDATE SET is_available=excluded.is_available;
 IF NOT EXISTS(SELECT 1 FROM public.menu_item_availability WHERE menu_item_id=meal AND campus_id=ca AND is_available=false) THEN RAISE EXCEPTION 'kitchen stock state not readable after save';END IF;
 UPDATE public.menu_item_availability SET is_available=false WHERE menu_item_id=meal AND campus_id=cb;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>0 THEN RAISE EXCEPTION 'kitchen changed foreign campus stock';END IF;
 UPDATE public.menu_item_availability SET is_available=true WHERE menu_item_id=meal AND campus_id=ca;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>1 THEN RAISE EXCEPTION 'kitchen cannot restock own campus';END IF;
 PERFORM set_config('role','none',true);PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 IF NOT EXISTS(SELECT 1 FROM public.menu_item_availability WHERE menu_item_id=meal AND campus_id=cb AND is_available=true) OR NOT EXISTS(SELECT 1 FROM public.menu_items WHERE id=meal AND is_available=true AND price=100) THEN RAISE EXCEPTION 'campus toggle changed parent catalog or foreign stock';END IF;
 UPDATE public.profiles SET role='student' WHERE id=actor;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',actor)::text,true);PERFORM set_config('role','authenticated',true);
 UPDATE public.menu_item_availability SET is_available=false WHERE menu_item_id=meal AND campus_id=ca;GET DIAGNOSTICS n=ROW_COUNT;
 IF n<>0 THEN RAISE EXCEPTION 'student changed kitchen stock';END IF;
 PERFORM set_config('role','none',true);
END $audit$;
ROLLBACK;
SELECT 'PASS: kitchen can save/read/restock own availability, cannot change foreign stock; student cannot write; global catalog and foreign row preserved; fixtures rolled back' AS evidence;
