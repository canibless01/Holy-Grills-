CREATE TABLE public.event_door_tokens (
 event_id uuid PRIMARY KEY REFERENCES public.events(id) ON DELETE CASCADE,
 qr_token text NOT NULL
);
ALTER TABLE public.event_door_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.event_door_tokens FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.event_door_tokens TO service_role;
CREATE POLICY event_door_tokens_service_only ON public.event_door_tokens FOR ALL TO service_role USING (true) WITH CHECK (true);
INSERT INTO public.event_door_tokens(event_id,qr_token)
 SELECT id,metadata->>'qr_token' FROM public.events WHERE NULLIF(metadata->>'qr_token','') IS NOT NULL;
CREATE FUNCTION public.hg_keep_event_door_token_private() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
BEGIN
 IF NULLIF(NEW.metadata->>'qr_token','') IS NOT NULL THEN
  IF COALESCE(auth.role(),'')<>'service_role' AND NOT public.hg_is_campus_admin(NEW.campus_id) THEN
   RAISE EXCEPTION 'Event QR permission denied' USING ERRCODE='42501';
  END IF;
  INSERT INTO public.event_door_tokens(event_id,qr_token) VALUES(NEW.id,NEW.metadata->>'qr_token')
  ON CONFLICT(event_id) DO UPDATE SET qr_token=EXCLUDED.qr_token;
  IF TG_OP='INSERT' THEN
   UPDATE public.events SET metadata=metadata-'qr_token' WHERE id=NEW.id;
  ELSE
   NEW.metadata=NEW.metadata-'qr_token';
  END IF;
 END IF;
 RETURN NEW;
END;$$;
REVOKE ALL ON FUNCTION public.hg_keep_event_door_token_private() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hg_keep_event_door_token_private() TO service_role;
-- UPDATE compatibility guard keeps legacy staff poster regeneration private.
CREATE TRIGGER trg_keep_event_door_token_private BEFORE UPDATE ON public.events
 FOR EACH ROW EXECUTE FUNCTION public.hg_keep_event_door_token_private();
CREATE TRIGGER trg_keep_inserted_event_door_token_private AFTER INSERT ON public.events
 FOR EACH ROW EXECUTE FUNCTION public.hg_keep_event_door_token_private();
UPDATE public.events SET metadata=metadata-'qr_token' WHERE metadata ? 'qr_token';
