-- Existing campus-scoped notification_blasts; table grants/RLS remain intact.
-- push_image is required by the composer in addition to the three requested fields.
ALTER TABLE public.notification_blasts
 ADD COLUMN IF NOT EXISTS body_html text,
 ADD COLUMN IF NOT EXISTS images jsonb NOT NULL DEFAULT '[]'::jsonb,
 ADD COLUMN IF NOT EXISTS cta_blocks jsonb NOT NULL DEFAULT '[]'::jsonb,
 ADD COLUMN IF NOT EXISTS push_image text;
ALTER TABLE public.notification_blasts
 ADD CONSTRAINT notification_blasts_images_shape CHECK (jsonb_typeof(images)='array' AND jsonb_array_length(images)<=6),
 ADD CONSTRAINT notification_blasts_cta_blocks_shape CHECK (jsonb_typeof(cta_blocks)='array' AND jsonb_array_length(cta_blocks)<=10),
 ADD CONSTRAINT notification_blasts_body_html_length CHECK (body_html IS NULL OR length(body_html)<=50000),
 ADD CONSTRAINT notification_blasts_push_image_length CHECK (push_image IS NULL OR length(push_image)<=2048);
-- No JSON GIN indexes: dispatch reads campaigns by id/status, never these arrays.
NOTIFY pgrst, 'reload schema';
