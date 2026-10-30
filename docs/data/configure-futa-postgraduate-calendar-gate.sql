-- Owner-authorized FUTA reference updates; no schema/table changes.
-- North Gate source: https://wjarr.com/sites/default/files/WJARR-2024-3109.pdf
-- Study-area reference corroborated by https://www.openstreetmap.org/node/4416374453
-- This is a published map reference, not a new field survey of the entrance.
BEGIN;
DO $config$
DECLARE cid uuid;
BEGIN
 SELECT id INTO STRICT cid FROM public.campuses WHERE slug='futa-main';
 INSERT INTO public.departments(name,slug,faculty,sort_order,campus_id,is_active)
 VALUES('Postgraduate','postgraduate','Postgraduate',52,cid,true)
 ON CONFLICT(campus_id,lower(name)) DO UPDATE SET faculty=excluded.faculty,is_active=true,updated_at=now();
 INSERT INTO public.academic_levels(name,value,rank,sort_order,campus_id,is_active)
 VALUES('Postgraduate','PG',0,6,cid,true)
 ON CONFLICT(campus_id,value) DO UPDATE SET name=excluded.name,is_active=true,updated_at=now();
 -- PG is not an undergraduate year rank and must not create automatic
 -- undergraduate graduation-bonus eligibility merely by being a later option.
 UPDATE public.academic_calendar SET start_date='2026-10-26',updated_at=now()
 WHERE campus_id=cid AND period_type='semester' AND academic_year='2026-2027'
 AND start_date='2026-10-19' AND is_active;
 -- Only replace the known old North Gate pin; never overwrite a concurrent
 -- owner correction. Prices and the unverified West/South pins are unchanged.
 UPDATE public.gates SET lat=7.30707,lon=5.13978,updated_at=now()
 WHERE campus_id=cid AND name='North Gate' AND abs(lat-7.31559096243868)<0.00000001 AND abs(lon-5.14126589717013)<0.00000001;
END $config$;
COMMIT;
SELECT jsonb_build_object('departments',(SELECT count(*) FROM public.departments WHERE campus_id=(SELECT id FROM public.campuses WHERE slug='futa-main') AND is_active),
 'postgraduate_levels',(SELECT count(*) FROM public.academic_levels WHERE campus_id=(SELECT id FROM public.campuses WHERE slug='futa-main') AND value='PG' AND is_active),
 'semester_start',(SELECT min(start_date) FROM public.academic_calendar WHERE campus_id=(SELECT id FROM public.campuses WHERE slug='futa-main') AND period_type='semester' AND academic_year='2026-2027' AND is_active),
 'north_gate',(SELECT jsonb_build_object('lat',lat,'lon',lon) FROM public.gates WHERE campus_id=(SELECT id FROM public.campuses WHERE slug='futa-main') AND name='North Gate')) AS verification;
