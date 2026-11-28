-- Optional: record which transport actually delivered each notification.
--
-- `notification_deliveries.status = 'sent'` cannot distinguish "OneSignal accepted"
-- from "OneSignal refused, Resend delivered" — which is the question that made a
-- delivery problem invisible and cost hours of reading TLS headers.
--
-- This migration is OPTIONAL. The application writes these columns when they exist
-- and silently falls back to the basic row when they do not, so nothing breaks if it
-- is never applied. Apply it to get per-provider counts in
-- `notification_blasts.metadata.dispatch[*].sent_by` and in the admin panel.

ALTER TABLE public.notification_deliveries
  ADD COLUMN IF NOT EXISTS provider      text,
  ADD COLUMN IF NOT EXISTS status_detail text;

COMMENT ON COLUMN public.notification_deliveries.provider IS
  'Which transport delivered this notification: resend | onesignal.';
COMMENT ON COLUMN public.notification_deliveries.status_detail IS
  'Human-readable note, e.g. "delivered by resend after onesignal refused".';
