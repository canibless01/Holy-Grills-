# Delivery batch assignment — 21 October 2026

This batch replaces per-order Python mutation loops with one private transaction for create, reassign/update, split and cancel. The isolated live transaction harness and controlled admin component browser checks passed. This is not a full delivery release sign-off.

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

## Migration and isolated live verification

Root reviewed and applied the SQL successfully once as server version **20261021092016**, name `delivery_batch_atomic`. Canonical file: `holy-grills-backend/migrations/20261021092016_delivery_batch_atomic.sql`, SHA-256 `5ed4e88e928eafd24e6fa6d48fbd5c57f439fe18e5aa80a71be3dac0fbdc42a0`. It creates one service-role-only RPC and replaces the existing batch progression trigger function, without adding a table or column. Post-apply signature/grant verification belongs to the integrated migration evidence.

The live harness `/workspace/work/ecosystem-audit/verify_delivery_batches.py` uses the journaled checkout20 campus, two newly journaled rider actors and synthetic **zero-value paid** order fixtures. It is not payment-provider or checkout-pricing proof. **All seven live cases passed**: failed mixed selections left no batch/assignments; create/replay retained one batch and the shared gate; reassignment updated effective ownership and refused the old rider; partial split/replay moved one selected order while leaving two in the source; an on-road batch refused cancellation and an attempted delivery stayed active; cancellation released every waiting order; concurrent creates produced one winner and no empty loser batch. Results: `/workspace/work/ecosystem-audit/checkout-20261020/batch-results.json`. No dataset cleanup or fixture deletion is performed.

The controlled browser harness `/workspace/work/ecosystem-audit/batch-20261021/browser.py` uses actual admin components with every API request intercepted. All four browser cases passed: eligible order/rider filtering and create retry key preservation; whole-batch reassignment; selected split and split retry key preservation; and cancellation requiring actual confirmation, with no request on dismissal and refreshed inactive controls after acceptance. The harness dismisses the actual Essential only cookie control and hides the unrelated storefront fixture root before mounting the admin component. No forced click or product change was introduced. Results: `/workspace/work/ecosystem-audit/batch-20261021/browser-results.json`; mobile screenshot: `/workspace/work/ecosystem-audit/batch-20261021/batch-mobile.png`. This controlled component test is not native routed Supabase persistence or real role authorization proof.

## Remaining scope

- The legacy automatic gate-staging helper remains unwired. This batch improves manual groups; it does not silently enable automatic staging on kitchen readiness.
- Native bulk kitchen preparation → ready → admin batch → rider delivery and payout still needs the broader operational browser matrix.
- Real rider notifications/push transport are not verified here. The saved transaction remains successful if optional follow-up notification delivery fails.
