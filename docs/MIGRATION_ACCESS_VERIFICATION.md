# Audit migrations: duplicate and access verification

Verified against Supabase **Test Two** on 2026-10-12. This covers the migrations introduced during this ecosystem audit, not a claim that every historical database object is clean.

## Objects and grants

| Object | Definitions | anon execute | authenticated execute | service_role execute |
| --- | ---: | --- | --- | --- |
| `credit_wallet_atomic(uuid,numeric,text,text,uuid,text,text,jsonb,uuid)` | 1 | denied | denied | allowed |
| `hg_create_order_atomic` (current 38-argument signature) | 1 | denied | denied | allowed |
| `hg_refund_order_atomic(uuid,uuid,text,numeric,text,boolean)` | 1 | denied | denied | allowed |
| `hg_redeem_flash_reward_atomic(uuid,uuid)` | 1 | denied | allowed | allowed |

All four functions pin `search_path=public`. Existing functions were replaced at their existing signatures; revisions did not create overloads. The refund function explicitly revokes PUBLIC, anon and authenticated access and grants only service_role. No additional table or index was introduced by these migrations.

Flash redemption intentionally remains callable by authenticated users. Actual authenticated RPC tests returned `feature_disabled` for the signed-in audit student while the release gate was off, and `forbidden` when that student supplied another student's ID. Catalogue cross-campus read/write attacks were also exercised with real account JWTs.

Catalogue guard policies occur once per table and operation. A comparison of table, operation, roles, policy mode and predicates found **zero duplicate groups among the added policies**. Separate INSERT and UPDATE guards are required to cover both operations. SELECT guards restrict anon/authenticated reads; write guards target authenticated roles. Existing permissive policies still determine which staff and owners can write, while the restrictive guards constrain campus and parent ownership.

## Migration revisions

The payment-state, admission, global-addon admission, catalogue boundary, flash-release, wallet-event serialization and refund migrations are present once each in migration history. The final refund correction uses the database's existing payment enum (`partially_refunded`, `refunded`, `failed`); it replaces the same refund function. Migration history intentionally retains revisions; they are not duplicate live functions.

No audit Storage bucket remains. Image ownership remains with Cloudinary.

## Effective access and transaction tests

- Student direct refund RPC access is denied. Student credit RPC access is unavailable through the Data API.
- Refund routes reject student, kitchen and rider actors; another campus's admin cannot see/refund the test order. No balance changes occur.
- Six concurrent cancellation calls across both cancellation routes safely reconcile an already credited historical test refund without another credit.
- Two independent equal-value partial refund intents each credit once, including four concurrent retries per intent. Preparation status remains unchanged and payment status becomes partially refunded.
- Four concurrent full-refund retries credit the remaining amount once and close the order.
- Six concurrent wallet credits for one provider event create one credit. Two separate equal-value provider events with the same generic reference each credit once.
- Actual admin UI simulation replaces a committed refund response with a 503. Retrying uses the same intent and creates one 100-naira credit in total.
- A rollback-only database test with a pending card portion rejects refunding uncollected card funds; customer cancellation returns only the collected wallet portion and restores redeemed HP. Test mutations are rolled back.

## Remaining security notices

Supabase advisors still identify historical SECURITY DEFINER functions callable by anon/authenticated, `pg_net` in public, newsletter-delivery RLS with no policies, and disabled leaked-password protection. These were not introduced by this batch and remain part of the full ecosystem security audit. The authenticated flash-redemption advisory is intentional and backed by ownership/release checks; the wallet, order creation and refund functions do not appear in the public-execute findings.

Advisor reference: [SECURITY DEFINER execute access](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable).

## Order-ticket access follow-up (2026-10-13)

`restrict_order_ticket_choices_to_visible_parents_and_server_writes` replaces the old ALL policy on the existing `order_addon_selections` table with one SELECT policy tied to a visible parent item and order. Anon has no table access; authenticated has SELECT only; service_role retains SELECT/INSERT/UPDATE/DELETE. No table or function is added.

Actual account tests reproduced kitchen insertion of a forged saved-choice snapshot (201) and customer inability to read their own three sides. After the migration, kitchen insertion returns 403, the owner/admin/kitchen read the three sides, foreign-campus actors read zero rows, and an unassigned rider reads zero rows. Every forged fixture is deleted by its exact ID. Rider access after assignment remains to be tested in the delivery loop.
