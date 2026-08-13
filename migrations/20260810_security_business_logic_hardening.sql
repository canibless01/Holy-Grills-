CREATE UNIQUE INDEX IF NOT EXISTS hp_transactions_unique_business_key_idx
ON public.hp_transactions (user_id, reference_type, reference_id)
WHERE reference_type IS NOT NULL AND reference_type <> ''
  AND reference_id IS NOT NULL;
