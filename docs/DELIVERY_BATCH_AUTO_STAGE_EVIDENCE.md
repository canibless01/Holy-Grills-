# Automatic ready-order staging — 21 October 2026

Paid orders entering ready from preparation now join an open, unassigned group for their campus, gate and recorded delivery window. The admin assigns the entire group to a rider through Manage / split → Assign staged batch. Until then, the orders remain ready with no delivery assignment or rider authorization.

Root reviewed and applied migration `20261021093327_stage_paid_ready_orders_by_gate_and_window.sql` once. SHA-256: `f04409b724064e7e6f74e4f598000b2b6732d2e7e38bb1cf97ae5e194fca12c0`. It replaces the existing dormant helper, adds one private trigger function and two statement triggers, and creates no table, column or function overload. Both functions retain service-only execute grants; the security-definer triggers invoke the helper internally for permitted kitchen writes. Public/customer direct helper execution remains denied.

Each helper locks its order before its campus/gate/window advisory lock and the candidate batch. It never locks another order after taking that advisory lock. Statement transition tables sort groups consistently for bulk preparation updates. A candidate must still be open with no rider after its row lock is acquired; otherwise a fresh waiting group is created. Existing manual assignment rechecks membership before changing effective rider authorization.

Missing or inactive gate mappings, foreign campus references and absent/foreign windows remain manual. A closed/inactive recorded window can still group its already-paid preparing orders: window closure stops new intake, rather than stranding fulfillment. Batch cancellation does not restage the released ready orders. This migration does not backfill historical ready orders.

## Verification

- Frontend typecheck and owned component ESLint passed.
- Nine live synthetic-fixture cases passed: grouping/replay, four concurrent transitions, staged membership protection, whole-group assignment, new groups after assignment/cancellation, manual fallback, competing create/stage, competing assignment/stage, concurrent multi-campus bulk updates and foreign gate/window rejection (related assertions are grouped in the journal). The first run stopped on a second-scope fixture missing required window times; a journal-checked continuation supplied those times and completed the remaining cases without replaying earlier mutations.
- Five controlled mobile admin browser cases passed, including assigning an open ready group, filtered manual creation/retry, reassignment, partial split/retry and confirmed cancellation.
- No cleanup or fixture deletion performed. Synthetic zero-value paid orders prove fulfillment grouping, not payment-provider behavior.

Full native rider delivery/payout and real push transport remain separate operational checks.
