-- Read-only counts and foreign-key dependencies. No emails, tokens or secret values.
SELECT 'auth_accounts' AS category,count(*) FROM auth.users
UNION ALL SELECT 'profiles',count(*) FROM public.profiles
UNION ALL SELECT 'auth_without_profile',count(*) FROM auth.users a LEFT JOIN public.profiles p ON p.id=a.id WHERE p.id IS NULL
UNION ALL SELECT 'orders',count(*) FROM public.orders
UNION ALL SELECT 'guest_orders',count(*) FROM public.orders WHERE user_id IS NULL
UNION ALL SELECT 'payments',count(*) FROM public.payments
UNION ALL SELECT 'menu_items_preserve_pending_classification',count(*) FROM public.menu_items
UNION ALL SELECT 'storefront_preserve_pending_classification',count(*) FROM public.storefront_sections
UNION ALL SELECT 'newsletter_subscriptions',count(*) FROM public.newsletter_subscriptions
UNION ALL SELECT 'stock_ledger',count(*) FROM public.stock_ledger;

SELECT conrelid::regclass::text AS dependent_table,confrelid::regclass::text AS parent_table,
 pg_get_constraintdef(oid) AS dependency
FROM pg_constraint WHERE contype='f' AND confrelid IN('public.profiles'::regclass,'auth.users'::regclass)
ORDER BY dependent_table,conname;

SELECT name,slug,is_active,
 CASE WHEN name ILIKE '%audit%' OR slug ILIKE 'audit%' OR slug ILIKE 'ecosystem-fix-audit%' THEN 'explicit_audit_candidate'
  WHEN slug='futa-main' THEN 'preserve_futa' ELSE 'preserve_until_classified' END AS proposed_scope
FROM public.campuses ORDER BY proposed_scope,name;
