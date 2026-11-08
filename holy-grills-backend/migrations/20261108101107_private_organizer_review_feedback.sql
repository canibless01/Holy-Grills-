CREATE TABLE hg_internal.event_organizer_reviews(event_id uuid PRIMARY KEY REFERENCES public.events(id) ON DELETE CASCADE,review_notes text,reviewed_by uuid REFERENCES public.profiles(id),submitted_at timestamptz);
ALTER TABLE hg_internal.event_organizer_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON hg_internal.event_organizer_reviews FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON hg_internal.event_organizer_reviews TO service_role;
CREATE POLICY organizer_reviews_service ON hg_internal.event_organizer_reviews TO service_role USING(true) WITH CHECK(true);
INSERT INTO hg_internal.event_organizer_reviews(event_id,review_notes,reviewed_by,submitted_at) SELECT id,review_notes,reviewed_by,submitted_at FROM public.events WHERE review_notes IS NOT NULL OR reviewed_by IS NOT NULL OR submitted_at IS NOT NULL;
DO $migration$
DECLARE definition text;
BEGIN
 definition:=pg_get_functiondef('public.hg_organizer_event_draft(uuid,uuid,text,jsonb)'::regprocedure);
 IF position('submitted_at=now(),' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected submission writer';END IF;
 definition:=replace(definition,'UPDATE public.events SET review_status=''submitted'',submitted_at=now(),is_published=false WHERE id=p_event RETURNING * INTO e;','UPDATE public.events SET review_status=''submitted'',is_published=false WHERE id=p_event RETURNING * INTO e; INSERT INTO hg_internal.event_organizer_reviews(event_id,submitted_at) VALUES(p_event,now()) ON CONFLICT(event_id) DO UPDATE SET submitted_at=EXCLUDED.submitted_at;');EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_review_organizer_event(uuid,uuid,text,jsonb)'::regprocedure);
 IF position('review_notes=p_data->>''notes''' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected review writer';END IF;
 definition:=replace(definition,'UPDATE public.events SET review_status=''approved'',is_published=true,review_notes=p_data->>''notes'',reviewed_by=p_actor WHERE id=p_event;','UPDATE public.events SET review_status=''approved'',is_published=true WHERE id=p_event; INSERT INTO hg_internal.event_organizer_reviews(event_id,review_notes,reviewed_by) VALUES(p_event,p_data->>''notes'',p_actor) ON CONFLICT(event_id) DO UPDATE SET review_notes=EXCLUDED.review_notes,reviewed_by=EXCLUDED.reviewed_by;');
 definition:=replace(definition,'UPDATE public.events SET review_status=''changes_requested'',is_published=false,review_notes=p_data->>''notes'',reviewed_by=p_actor WHERE id=p_event;','UPDATE public.events SET review_status=''changes_requested'',is_published=false WHERE id=p_event; INSERT INTO hg_internal.event_organizer_reviews(event_id,review_notes,reviewed_by) VALUES(p_event,p_data->>''notes'',p_actor) ON CONFLICT(event_id) DO UPDATE SET review_notes=EXCLUDED.review_notes,reviewed_by=EXCLUDED.reviewed_by;');EXECUTE definition;
 definition:=pg_get_functiondef('public.hg_organizer_event_balance(uuid,uuid)'::regprocedure);
 IF position('''event'',to_jsonb(e),''earned''' IN definition)=0 THEN RAISE EXCEPTION 'Unexpected owned event reader';END IF;
 definition:=replace(definition,'''event'',to_jsonb(e),''earned''','''event'',to_jsonb(e)||coalesce((SELECT to_jsonb(review)-''event_id'' FROM hg_internal.event_organizer_reviews review WHERE review.event_id=p_event),''{}''::jsonb),''earned''');EXECUTE definition;
END $migration$;
ALTER TABLE public.events DROP COLUMN review_notes,DROP COLUMN reviewed_by,DROP COLUMN submitted_at;

