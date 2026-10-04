-- ═══════════════════════════════════════════════════════════════════════════
--  SEED the Support / WhatsApp keys — 2026-10-04
--
--  WHY THIS FILE EXISTS
--  --------------------
--  The floating "Chat with us" button is rendered for every visitor, so it
--  cannot read /admin/settings. Its only source is:
--
--      system_settings (is_public = TRUE)
--        → GET /storefront/config/public
--        → featureConfig.loadSystemSettings()
--        → WhatsAppFloatingButton → https://wa.me/<number>
--
--  Two things broke that chain, and both looked like "the button isn't reading
--  the table":
--    1. none of these three keys had a row, so the button used the hardcoded
--       frontend default (2348000000000) no matter what was typed anywhere;
--    2. a row created from the admin screen was inserted WITHOUT is_public, so
--       it took the column default (false) and was filtered out of the public
--       config — saved, listed for admins, never used by the app.
--  Both are fixed by the rows below.
--
--  HOW TO RUN
--    Supabase dashboard → SQL Editor → paste this whole file → Run.
--    Idempotent: a key is inserted only when no global row exists for it, so
--    running it twice changes nothing and an admin's live value is never
--    overwritten.
-- ═══════════════════════════════════════════════════════════════════════════

DO $$
DECLARE
  r          record;
  v_type     text;
  v_as_json  boolean;
  v_has_public boolean;
  v_cols     text;
  v_vals     text;
  v_existing boolean;
  v_seeded   text[] := '{}';
BEGIN
  IF to_regclass('public.system_settings') IS NULL THEN
    RAISE EXCEPTION 'public.system_settings does not exist — nothing seeded';
  END IF;

  SELECT data_type INTO v_type
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'system_settings' AND column_name = 'value';
  IF v_type IS NULL THEN
    RAISE EXCEPTION 'system_settings.value column not found — nothing seeded';
  END IF;
  v_as_json := v_type IN ('json', 'jsonb');

  SELECT count(*) FILTER (WHERE column_name = 'is_public') > 0
    INTO v_has_public
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'system_settings';

  FOR r IN
    SELECT * FROM (VALUES
      -- (key, value, description)
      ('whatsapp_support_number',  '2348000000000', 'Support WhatsApp number in international format (digits only, e.g. 2348012345678) — read by the floating "Chat with us" button via GET /storefront/config/public'),
      ('whatsapp_support_enabled', 'true',          'Show the floating WhatsApp support button in the app — read by WhatsAppFloatingButton'),
      ('whatsapp_support_message', 'Hello, I need help with my order', 'Prefilled WhatsApp message; replaced by the order number when the user has an active order')
    ) AS t(key, value, description)
  LOOP
    EXECUTE format(
      'SELECT EXISTS (SELECT 1 FROM public.system_settings s WHERE s.key = %L AND s.campus_id IS NULL)',
      r.key
    ) INTO v_existing;

    IF v_existing THEN
      CONTINUE;
    END IF;

    v_cols := 'key, value, description, campus_id';
    v_vals := format('%L, %s, %L, NULL',
                     r.key,
                     CASE WHEN v_as_json THEN format('%L::jsonb', r.value)
                          ELSE format('%L', r.value) END,
                     r.description);
    IF v_has_public THEN
      v_cols := v_cols || ', is_public';
      -- Public on purpose: the number is printed in the UI for every visitor,
      -- so publishing it from the table discloses nothing — and a private row
      -- would simply never reach the button.
      v_vals := v_vals || ', TRUE';
    END IF;

    EXECUTE format('INSERT INTO public.system_settings (%s) VALUES (%s)', v_cols, v_vals);
    v_seeded := v_seeded || r.key;
  END LOOP;

  RAISE NOTICE 'seed_whatsapp_support_settings: inserted % row(s): %',
               coalesce(array_length(v_seeded, 1), 0), coalesce(array_to_string(v_seeded, ', '), '(none)');
END $$;


-- ───────────────────────────────────────────────────────────────────────────
--  If a row for one of these keys already existed but was private (the case
--  this bug was reported for: the number is visible in the admin list yet the
--  button keeps opening the default), publicise it. The value is untouched.
--
--  Safe to re-run; only touches these three keys.
-- ───────────────────────────────────────────────────────────────────────────
UPDATE public.system_settings
   SET is_public = TRUE
 WHERE key IN ('whatsapp_support_number', 'whatsapp_support_enabled', 'whatsapp_support_message')
   AND is_public IS DISTINCT FROM TRUE;


-- ───────────────────────────────────────────────────────────────────────────
--  Verify
--
--    SELECT key, value, campus_id, is_public
--      FROM public.system_settings
--     WHERE key LIKE 'whatsapp_%'
--     ORDER BY key, campus_id NULLS FIRST;
--
--  Then, with no X-Campus-ID header (or the campus you are scoping to):
--
--    GET /api/storefront/config/public
--
--  must contain `whatsapp_support_number` with the value above. If it does
--  not, the row is still private or the caller is sending a campus id that
--  has no row for the key (a campus-scoped read only sees global rows plus
--  that campus's own rows).
-- ═══════════════════════════════════════════════════════════════════════════
