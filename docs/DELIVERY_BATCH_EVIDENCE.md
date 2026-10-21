# Delivery batch assignment — 21 October 2026

This batch replaces per-order Python mutation loops with one private transaction for create, reassign/update, split and cancel. It is not a complete delivery release sign-off until the live transaction and browser harnesses below have passed.

## Behavior

- Only paid, ready, unbatched orders enter a new manual batch. Campus/window/rider checks are revalidated against locked rows. Mixed invalid selections reject the entire batch.
- Existing batches lock their orders before the batch, matching rider progression's order → batch lock order. An assignment UPSERT updates explicit per-order rider overrides as well as batch defaults, so reassignment and partial splits change effective authorization consistently.
- Client-generated batch UUIDs remain stable across retries within the create/split dialog. Saved retries return the existing batch and skip duplicate notification/audit follow-up.
- A split must leave at least one order in the source batch. Only assigned, paid selected orders move; orders already on the road remain with their rider.
- Cancellation releases all waiting orders and assignments in one transaction, with attributed per-order logs. An on-road/failed-attempt order prevents cancellation.
- Failed delivery attempts remain operationally active, instead of completing the batch and disappearing from the rider's active list.
- Same-gate manual groups persist their configured gate reference for the existing rider sequencing logic. Deliberately mixed manual groups remain possible and have no single gate reference.
- The admin UI adds Manage / split, whole-batch reassignment and selected-order splitting. Ready-order pickers filter campus/window/payment/readiness, and stale preset selections are explained. An unavailable unrelated delivery read no longer leaves the entire page indefinitely loading.

## Verification completed locally

- `tests.test_delivery_batch_transactions`: six HTTP boundary tests passed (actor/intent binding, invalid bulk requests, database error mapping, split/cancel RPC routing and replay side-effect suppression).
- Those tests together with `tests.test_order_role_boundaries`: **12 passed**.
- Frontend TypeScript and owned-file ESLint checks passed.
- Owned-path `git diff --check` passed.

## Pending parent-run proofs

SQL draft: `docs/DELIVERY_BATCH_ATOMIC_FIX.sql`, SHA-256 `5ed4e88e928eafd24e6fa6d48fbd5c57f439fe18e5aa80a71be3dac0fbdc42a0`. It has not been applied by this agent. It creates one service-role-only RPC and replaces the existing batch progression trigger function, without adding a table or column. After root review/application, record the server migration version and matching canonical file name; verify one function signature and private grants.

The live harness `/workspace/work/ecosystem-audit/verify_delivery_batches.py` uses the journaled checkout20 campus, two newly journaled rider actors and synthetic **zero-value paid** order fixtures. It is not payment-provider or checkout-pricing proof. It tests failed mixed selections, create/replay/gate mapping, reassignment and old-rider refusal, split/replay, on-road cancellation refusal, failed-attempt visibility, cancellation release and concurrent competing creates. No dataset cleanup or fixture deletion is performed.

The controlled browser harness `/workspace/work/ecosystem-audit/batch-20261021/browser.py` uses actual admin components with every API request intercepted. It tests eligible order/rider filtering, create retry key preservation, whole-batch reassignment, selected split and split retry key preservation. It is not Supabase persistence or real role authorization proof.

## Remaining scope

- The legacy automatic gate-staging helper remains unwired. This batch improves manual groups; it does not silently enable automatic staging on kitchen readiness.
- Native bulk kitchen preparation → ready → admin batch → rider delivery and payout still needs the broader operational browser matrix.
- Real rider notifications/push transport are not verified here. The saved transaction remains successful if optional follow-up notification delivery fails.
