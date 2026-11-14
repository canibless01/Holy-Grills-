-- Remove an identical historical BEFORE UPDATE guard, retaining the canonical
-- guard after the graduation validator. Neither validator mutates role/balances.
-- No function definition or authorization behavior changes.
BEGIN;
DO $deduplicate$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger
    WHERE tgrelid='public.profiles'::regclass
      AND tgname='trg_profiles_protect_columns'
      AND tgfoid='public.hg_protect_profile_columns()'::regprocedure
      AND tgtype=19 AND tgenabled='O' AND tgqual IS NULL
      AND tgnargs=0 AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'Canonical enabled profile guard is required';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_trigger
    WHERE tgrelid='public.profiles'::regclass
      AND tgname='hg_protect_profile_columns_trg') THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_trigger
      WHERE tgrelid='public.profiles'::regclass
        AND tgname='hg_protect_profile_columns_trg'
        AND tgfoid='public.hg_protect_profile_columns()'::regprocedure
        AND tgtype=19 AND tgenabled='O' AND tgqual IS NULL
        AND tgnargs=0 AND NOT tgisinternal
    ) THEN
      RAISE EXCEPTION 'Profile guard differs; manual comparison is required';
    END IF;
    DROP TRIGGER hg_protect_profile_columns_trg ON public.profiles;
  END IF;
END
$deduplicate$;
COMMIT;
