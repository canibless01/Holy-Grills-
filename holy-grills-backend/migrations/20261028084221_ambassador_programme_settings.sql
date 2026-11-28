-- ============================================================================
-- Campus Ambassador Programme — 4/4 — global configuration seed
-- ----------------------------------------------------------------------------
-- Idempotent: existing keys are left untouched so Admin-tuned values survive
-- a re-run. All rows are global (campus_id IS NULL); edit them later through
-- the existing system-settings admin surface.
-- ============================================================================

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('ambassador_attribution_window_days',        '7',
       'Rolling last-click attribution window for ambassador order credit (days)'),
      ('ambassador_expected_weekly_shares',         '4',
       'Promotional shares an ambassador is expected to confirm per week'),
      ('ambassador_meal_discount_default_max',      '3000',
       'Default maximum eligible meal value (NGN) for an ambassador meal discount'),
      ('ambassador_meal_discount_default_validity', '14',
       'Default validity in days of a newly granted ambassador meal discount')
    ) AS v(key, value, description)
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM public.system_settings
      WHERE key = r.key AND campus_id IS NULL
    ) THEN
      INSERT INTO public.system_settings (key, value, campus_id, is_public, updated_at)
      VALUES (r.key, r.value::jsonb, NULL, false, now());
    END IF;
  END LOOP;
END $$;
