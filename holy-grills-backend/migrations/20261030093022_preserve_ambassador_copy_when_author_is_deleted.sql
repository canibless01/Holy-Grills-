-- Preserve intentional programme copy when a test/retired author is removed.
-- No table, function, policy or role grant is added.
ALTER TABLE public.ambassador_promo_messages ALTER COLUMN created_by DROP NOT NULL;
DO $$ DECLARE constraint_name text; BEGIN
FOR constraint_name IN
 SELECT c.conname FROM pg_constraint c
 JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
 WHERE c.conrelid='public.ambassador_promo_messages'::regclass
 AND c.confrelid='public.profiles'::regclass AND c.contype='f' AND a.attname='created_by'
LOOP
 EXECUTE format('ALTER TABLE public.ambassador_promo_messages DROP CONSTRAINT %I',constraint_name);
END LOOP;
END $$;
ALTER TABLE public.ambassador_promo_messages
 ADD CONSTRAINT ambassador_promo_messages_created_by_fkey
 FOREIGN KEY(created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;
