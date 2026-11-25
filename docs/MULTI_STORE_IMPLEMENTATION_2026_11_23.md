# Multi-store fulfilment — implementation and release record

Updated 25 November 2026. **Implemented in source; store ordering remains disabled.** This record replaces the original design's assumptions where the owner subsequently requested uniform campus operations.

## Implemented scope

- University → campus → store hierarchy, with super-admin university/campus linkage and campus-admin store/team management. Stores have validated addresses, paired coordinates, capabilities and active state. Writes use replay keys or optimistic versions; team changes validate fresh role, activity and campus and record audit entries atomically.
- All stores in a campus use the same menu, prices, promotions, inventory, capacity, opening/closing rules and ordering/delivery windows. No store-specific menus, schedules or stock ledgers were added.
- Checkout offers eligible stores, suggests the closest serving store for a destination pin, and validates the shared campus delivery radius from the store origin. Existing hostel/gate tariffs remain authoritative. Pickup uses the selected store's address/instructions and the existing pickup flag. Stale selections revalidate before checkout.
- Orders retain immutable store identity/address snapshots; legacy orders stay unassigned rather than receiving invented attribution. Existing wallet/card/split, payment recovery, rewards and refunds continue through the original financial helpers.
- Separate batches per store/date/window/gate, with shared campus admission capacity. Kitchen views can filter assigned stores; RLS and server checks independently reject unauthorized store work. Rider assignment/splitting verifies store membership. Paid due-day preparation still follows the shared campus cutoff.
- Kitchen, admin batch management, customer confirmation and rider cards display the fulfilling store. Admin assignment choices use eligible store riders; admin and rider route sequencing start at the stored origin. Delivered rider history remains readable after team removal, while further store updates are denied.
- Store performance reports expose campus/store/date views, super-admin university filtering, paid volume, completed refunds, retained food/delivery revenue, counts and CSV. Unpaid and test amounts are excluded from revenue. Reports group by order creation date and include refunds recorded so far; they are not a bank settlement or profitability report.
- Feature activation fails closed when dispatch readiness cannot be verified. No operational stores or team assignments were fabricated, and no feature was enabled.

## Migration ledger

Test Two project: `zaxdkrmzyibkvlsrgmvq`. Migration history was checked again after the owner reconnected Supabase.

| Migration | Test Two state |
| --- | --- |
| `20261123151643_multi_store_configuration.sql` | Applied once |
| `20261123153118_store_order_attribution.sql` | Applied once |
| `20261123153119_store_batch_scope.sql` | Applied once |
| `20261123153234_store_fulfilment_release_gate.sql` | Applied once |
| `20261123153609_store_live_readiness.sql` | Applied once |
| `20261125085607_store_batch_group_key.sql` | Applied once, 25 November |
| `20261125085616_store_dispatch_readiness.sql` | Applied once, 25 November |

The index migration replaces the old open-batch key with disjoint legacy/store keys, allowing two stores to serve the same gate/window. The dispatch migration supplies dispatch readiness, eligible rider lookup and bounded private RLS helpers, and preserves historical rider completion/payout access after membership removal. Both are now applied; live rollback verification passed on 25 November. Operational browser acceptance is still required before activation. Previous timed-out application attempts have uncertain outcomes until history is inspected: check history first, never blindly reapply. If an older payload appears, compare its function definitions and add a follow-up migration for differences.

New configuration tables have RLS enabled and no browser table grants. Public RPCs are service-only invokers. Private policy helpers bind their checks to `auth.uid()` and a fixed search path; the private schema is not exposed. Advisors reported no new store-related warning; intentional RLS-without-policy information reflects backend-only configuration tables, not a reason to grant broad access.

## Verification completed

- Full backend suite: 2,046 passed. A subsequent admin batch origin/eligible-rider regression and the existing batch transaction tests passed together (26 tests).
- Frontend typecheck, lint, message-registry validation and separate client/server production builds passed. The full build chain passed its preliminary regressions, then stopped at the existing canonical-origin test when the environment denied an esbuild subprocess (`EPERM`); it is not recorded as a full-build pass.
- Fresh seven-migration installation passed in a disposable PostgreSQL 17 copy, followed by all three rollback SQL fixtures below. The copy predates some production base policies, so the test deliberately used broad permissive baseline policies to challenge the new restrictive store policies. This is **not** a complete production-policy clone or proof of every existing production permission.
- `tests/sql/store_configuration_rollback.sql`: create/replay, conflicting edits, university links, staff role/campus validation, audit atomicity and grants.
- `tests/sql/store_order_to_rider_rollback.sql`: guest card pending/verified replay, wallet debit, unpaid preparation refusal, shared capacity across two stores, separate same-gate batches, kitchen RLS/cross-store denial, rider assignment/foreign-store denial, delivery/batch completion, partial-refund replay and conservation, frozen store address and delivered rider history after membership removal.
- `tests/sql/store_selected_pickup_rollback.sql`: selected-store wallet order/replay, future/unpaid preparation guards, collection replay, fulfillment of already-paid orders after the pickup flag is disabled, zero delivery fee/no rider/no mode switching and unchanged delivery path. Existing legacy pickup rollback regression also passed.
- Earlier live Test Two configuration tests passed. The live two-store flow passed payment/admission and cross-store kitchen checks, then exposed the old unique batch index when the second store became ready. The corrected complete flow passed locally; all three corrected live fixtures subsequently passed on Test Two on 25 November, including the actual production RLS policies.
- No real gateway charge, customer email, notification blast, live test-data seed or cleanup was performed.

## Release checks still required

1. Completed 25 November: SQL connectivity recovered, both migrations applied once with their actual history versions, and all three rollback fixtures passed on Test Two. The earlier timeout was an execution limitation, not evidence of application. Source filenames now match applied versions.
2. Completed 25 November: live catalogue review and rollback tests check actual RLS/grants, disjoint legacy/store batch indexes and helper identities. New configuration tables remain private to the backend. No second store schema or duplicate helper signature was added.
3. Configure real store addresses/coordinates and active kitchen/rider memberships, then exercise the checkout → kitchen → rider and pickup interfaces in a browser. Native Chromium is blocked before launch by this execution environment's socket restrictions; API/SQL tests do not replace visual acceptance.
4. Verify deployed provider payment/receipt behavior using the established operational acceptance process before activating the flag. Provider execution was not exercised here.

## Explicit remaining hierarchy scope

Within-campus store choice is implemented. Logged-in ordering still uses the account's existing campus; a separate customer ordering-campus switch independent of academic/staff identity is **not implemented**. Registration has not been rewritten to select university first. University links currently serve configuration and reporting. That wider physical-campus browsing/cart-context feature must be completed and tested separately before claiming university-wide roaming ordering.
