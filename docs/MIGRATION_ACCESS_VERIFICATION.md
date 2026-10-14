# Audit migrations: duplicate and access verification

Verified against Supabase **Test Two** through 2026-10-13. This covers the migrations introduced during this ecosystem audit, not a claim that every historical database object is clean.

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

## Order role boundaries follow-up

The preparation-boundary migrations replace the existing `hg_protect_order_columns()` trigger function at its existing zero-argument signature. They add no trigger, table or overload. The trigger checks direct authenticated writes in addition to API checks: kitchen can only move to preparing/ready; preparation and delivery require collected payment; cancellation/refund state changes require the service-backed atomic actions. Existing rider ownership and state-machine triggers remain in effect.

Rollback-only SQL reproduced kitchen walking a ready, unassigned order all the way to delivered. After the fix, the first assignment transition returns `42501:kitchen_preparation_only` and the order remains ready. Another rollback-only test returns `42501:payment_required_for_preparation` for an unpaid order. Actual API tests reject kitchen assignment/walking to delivery, bulk advancement from ready, and admin cancellation through a plain status PATCH, without changing the owned ready order. Actual admin batching and assigned-rider pickup/delivery still succeed.

## Atomic review follow-up

`hg_submit_order_review_atomic(uuid,uuid,integer,integer,integer,text,integer,integer,text[])` has exactly one live definition, pins its search path, and allows only service_role execution. It reuses `order_reviews`, `monthly_hp_tracker` and `record_hp_transaction_atomic`; no table, index or column is added. Revision history retains the final retry/image comparison update without creating an overload.

Actual UI response-loss retry saves one review and one 20-HP pending transaction, renders all sub-ratings in admin and the menu rating/count, and remains saved after reload. Six simultaneous API replays leave the HP ledger and monthly tracker unchanged. A rollback-only capped-allowance test awards five HP when five remain; a deliberately rejected HP insert leaves zero reviews and the monthly total unchanged.

Public EXECUTE on the existing order column-guard trigger function was also revoked. Both anon and authenticated now lack direct function execution, service_role retains it, and a real authenticated kitchen identity can still make a permitted preparation update through the table trigger (verified in a rolled-back transaction).

## Order-lock pricing, access and fulfilment follow-up

Three migrations are each present once: `apply_order_lock_discounts_once_and_enforce_payment_conservation`, `restrict_order_lock_mutations_to_validated_backend`, and `credit_order_lock_hp_only_when_fulfilled`. Revisions retain one live 38-argument order-admission function and one zero-argument order guard; no new table, column, index, trigger or function overload is introduced. The historical ORDER_STATE_RPC_FIX.sql now points to the canonical admission definition rather than overwriting newer fixes.

`order_locks` has one owner/admin SELECT policy. Anon has no table access; authenticated has SELECT only; service_role can SELECT/INSERT/UPDATE/DELETE. Direct authenticated UPDATE returns permission denied. Existing lock/order trigger functions deny anon/authenticated EXECUTE while their installed triggers still execute normally. Order creation remains service-only, and all three functions pin `search_path=public`. Added-policy duplicate groups for lock and saved-choice tables: zero.

The current admission definition validates that subtotal minus food discounts plus delivery equals total, and wallet plus card equals that same total. A rollback test with uncovered payment amounts returns ORDER_PAYMENT_CONSERVATION with no order or debit. Discount locking validates owner, campus, active status and today's Lagos date without subtracting the discount twice.

HP-lock credit moves from order admission into the existing order-update trigger at delivery. The existing HP ledger business key prevents repeat credit and recognizes legacy awards. Rolled-back cancellation preserves zero bonus; valid paid preparation/assignment/delivery writes produce one 100-HP bonus. The raw HP ledger and tier functions were also checked and already deny anon/authenticated execution; no grant change to them was necessary. Security advisors were rerun; historical notices listed above remain open.

## Global feature flags and historical duplicate-trigger cleanup

`restrict_global_feature_flags_to_active_super_admins` appears once in migration history and replaces the existing `feature_flags_admin_write` policy by name. Its USING and WITH CHECK use `hg_is_campus_admin(NULL::uuid)`, which requires a fresh active super-admin profile. Writes require a global row. Anon/authenticated retain SELECT; authenticated INSERT/UPDATE/DELETE remain constrained by RLS; service_role retains those data operations. Authenticated TRUNCATE and anonymous UPDATE are denied. There is one write policy, zero campus-specific flag rows and zero remaining audit flag rows.

Actual JWT/rollback tests show a deactivated super admin cannot update flags, an active super admin can, and a campus admin cannot. The existing helper is reused; no new table, column, function or overload is introduced. Advisors were rerun and the historical notices above remain open.

`remove_identical_profile_column_guard_trigger` appears once and removes only `hg_protect_profile_columns_trg`, after comparing its function, event, enabled status, arguments and predicate with the retained canonical `trg_profiles_protect_columns`. Exactly one enabled profile column guard remains. Its execution grants and function definition remain unchanged. After cleanup, authenticated own-profile edits succeed and direct role/HP/wallet forgery still returns permission denied, all verified in rolled-back transactions.

## Exclusive-spin transaction and grant follow-up

`make_exclusive_spin_awards_and_credit_grants_atomic` occurs once. `hg_spin_exclusive_atomic(uuid,uuid)` and `hg_grant_exclusive_spins_atomic(uuid,uuid,uuid,integer,integer,text)` each have one definition, pin `search_path=public`, deny PUBLIC/anon/authenticated EXECUTE and allow service_role. They use fresh active profiles, exact campus ownership and per-target profile locks. The spin release gate is checked inside the transaction after recovering any existing receipt.

Existing tables receive four columns used by these flows: `exclusive_spin_prizes.reward_config`, `exclusive_spin_fulfillments.intent_key/result_snapshot`, and `exclusive_spins.grant_snapshot`. One partial unique index on fulfilment `(user_id,intent_key)` protects the spin business key. Admin-grant identities use the credit table's existing primary key. No new table, trigger or function overload is created. Known existing +300/+750 HP and free-delivery prizes are configured to preserve their effects; other existing prize names keep their former manual fulfilment behavior until categorized by an admin.

Authenticated users have SELECT only on credits. Fulfilment SELECT retains owner/admin RLS; staff UPDATE is restricted to `status`, `fulfilled_by`, `fulfilled_at` and existing campus RLS. Authenticated INSERT, snapshot UPDATE and credit replenishment are denied. Prize-pool SELECT/INSERT/UPDATE/DELETE remain campus-policy controlled; authenticated TRUNCATE and all anon access are denied. Active-prize reads are global or within the reader's campus.

Actual browser/API concurrency and response-loss tests record one grant, one HP award per intent and one admission for the final credit. Rolled-back forced HP failure preserves credit/balance and creates no receipt. A grant retry after expenditure cannot mint replacement credits. SQL tampering attempts are denied. Security advisors retain the same historical findings above; neither new private transaction function appears in the public-execute findings.

## Primary delivery HP recovery follow-up

`consume_delivery_hp_multiplier_with_atomic_payout` appears once. The prior five-argument `hg_credit_delivery_hp_atomic` definition is explicitly removed, leaving one seven-argument definition with defaults for `p_expected_multiplier` and `p_total_hp_amount`. Actual Data API calls with either five or seven named arguments replay the same already credited audit delivery. No overlapping overload, table, column, index or trigger is created.

The current function pins `search_path=public`, denies PUBLIC/anon/authenticated EXECUTE and grants service_role. It validates a paid, delivered order and its owner, locks the profile, checks the calculated multiplier, then commits the existing HP ledger, monthly tracker, multiplier reset and complete order HP marker together. A zero-food delivery retains the food multiplier. A stale multiplier returns without mutations. Forced insert failure rolls back all affected state. Replays do not consume a subsequently granted bonus. Security advisors retain the historical findings above.


## Storefront campus and guest-grant follow-up

`enforce_storefront_campus_reads_and_restrict_cms_grants` and `restrict_anonymous_cms_writes` each occur once in migration history. The former adds one restrictive SELECT policy on each existing CMS table; the latter removes anonymous INSERT/UPDATE/DELETE grants. Neither adds a table, column, index, function or trigger. Canonical SQL is in [STOREFRONT_CAMPUS_SCOPE_FIX.sql](STOREFRONT_CAMPUS_SCOPE_FIX.sql).

On `banners` and `storefront_sections`, anon retains SELECT only. Authenticated retains staff SELECT/INSERT/UPDATE/DELETE, constrained by existing campus RLS; TRUNCATE/REFERENCES/TRIGGER are revoked for both public client roles. Service-role privileges are preserved. Policy comparison reports zero duplicate groups. The existing section key/campus uniqueness constraint is reused for intent conflicts and overrides.

Before the read guard, an anonymous caller and a foreign-campus student could read fifteen active audit-campus CMS rows directly. After the guard they read zero. Bounded backend guest reads still supply the validated selected campus's public content. An actual rolled-back authenticated role test against an owned CMS row returns:

| Actor | Read rows | Update rows |
| --- | ---: | ---: |
| Own-campus student | 1 | 0 |
| Own-campus admin | 1 | 1 |
| Foreign-campus student/admin | 0 | 0 |
| Own-campus kitchen/rider | 1 | 0 |
| Active super admin | 1 | 1 |

Actual browser sessions also verify super admin can create and edit an inactive global section without selecting a campus; a campus admin's edit is rejected with 404. The exact global probe is deleted. Per-slide configuration reuses existing JSON, so it introduces no migration object or grants. The general support email reuses one existing-setting key and has exactly one global row.

Security advisors were rerun after the grant change. Historical SECURITY DEFINER exposure, `pg_net` location, newsletter-delivery policy and password-protection notices remain under the wider security audit; this batch is not a database-wide clean bill of health.


## Delivery-benefit admission and restoration

`claim_delivery_benefits_with_atomic_checkout` appears once in migration history. It reuses the existing spin receipts, monthly-perk claims and order status logs. One `exclusive_spin_fulfillments.applied_order_id` foreign-key column and one partial pending-delivery index are added. There is no new table or function overload. The three canonical transaction definitions in [DELIVERY_BENEFIT_ATOMIC_FIX.sql](DELIVERY_BENEFIT_ATOMIC_FIX.sql) match their live definitions.

`hg_create_order_atomic`, `hg_spin_exclusive_atomic`, `hg_refund_order_atomic` and `hg_prize_status_guard` each have one definition, a pinned search path, no anon/authenticated EXECUTE and service-role execution. The guard's public execution privilege is removed while installed triggers remain functional. One restrictive authenticated UPDATE policy limits staff fulfilment to physical or legacy untyped receipts. Direct authenticated attempts to mark an automatic delivery credit fulfilled affect zero rows; the staff API rejects the same operation with 409.

Checkout claims the server-quoted monthly benefit, legacy cap or exact pending receipt in the same transaction as admission and payment. Wallet/profile locks and immutable receipt snapshots prevent concurrent use of one credit. A failed debit rolls back the claim and order; idempotent replay returns the original admission. Existing pre-preparation cancellation rules restore the exact receipt or monthly claim, once. Later-preparation and partial-refund benefit policies remain under audit.

Rolled-back transaction proofs cover legacy caps, separate queued receipts, monthly precedence, stale admission, replay, cancellation restoration, insufficient-wallet rollback, changed prize configuration and denied staff mutation. Security advisors were rerun: the exposed SECURITY DEFINER counts are now 13 anonymous and 24 authenticated, with the existing newsletter-policy, extension-location and password-protection findings still open. This is not database-wide security sign-off.

## Order card-payment recovery and unpaid fulfilment

`recover_order_card_payments_with_bound_provider_receipts` and `prevent_unpaid_order_fulfilment` each appear once. They replace existing `hg_mark_order_paid(uuid,text,text,numeric,jsonb)` and `hg_verify_order_status_transition()` definitions without new tables, columns, indexes, triggers or overloads. One existing `trg_orders_state_machine` remains. Canonical SQL is in [ORDER_CARD_PAYMENT_RECOVERY_FIX.sql](ORDER_CARD_PAYMENT_RECOVERY_FIX.sql) and [ORDER_PAYMENT_FULFILMENT_GUARD.sql](ORDER_PAYMENT_FULFILMENT_GUARD.sql).

Both functions pin the search path, deny PUBLIC/anon/authenticated execution and permit service_role. Anonymous users have no `payments` table privileges. Authenticated users retain SELECT under existing owner/admin RLS, with INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER revoked; service-role writes remain permitted. Existing payment-reference uniqueness is reused. No policy is added or duplicated.

Rolled-back live SQL confirms the split card remainder, one receipt on replay, no automatic preparation, wrong-amount rejection, cross-order reference rejection, cancellation-versus-confirmation exclusion and no wallet credit for an unpaid cancellation. An unpaid preparation attempt is rejected by the trigger. Actual role/API tests also reject kitchen preparation of a pending order. Concurrent signed fixture webhook and verification produce one paid receipt; the audit wallet reconciles to its original balance after labelled simulation cleanup.

Advisors were rerun and still return the historical newsletter-policy, extension-location, exposed-helper and password-protection categories. Direct privilege checks above prove the changed functions are private; advisory counts are not treated as a whole-database sign-off. Wider historical remediation belongs to Workstream B. Relevant [function search-path guidance](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable) and [extension-location guidance](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public) remain available for that review.


## Workstream B live migrations — 14 October 2026

See [Workstream B evidence matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md) and [selected test traces](WORKSTREAM_B_TEST_EVIDENCE.json). B is not complete. Six owned-domain migrations are live once each on Test Two; the matrix lists canonical SQL, checked grants/signatures and deployment dependencies. All exact owned synthetic fixture rows and eight Auth accounts were removed after deactivation/logout. No global release settings changed. Main at `723825e` was merged normally. Integrated backend regression: 209 tests pass; frontend typecheck/build checks recorded in matrix. Provider delivery, marketplace gated purchases, paid event recovery/refunds, broad onboarding/admin/reporting coverage and historical advisory closure remain open.
