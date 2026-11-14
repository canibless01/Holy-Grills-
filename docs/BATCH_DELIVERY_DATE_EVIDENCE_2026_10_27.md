# Delivery batch dates — 27 October 2026

Merged user changes through `499d374` before continuing. The signup onboarding editor still supports only free-side credits; generalized promotion benefits remain open.

## Defect and correction

A rolled-back Test Two reproduction placed two paid, scheduled, ready orders seven days apart against the same repeating delivery-window UUID. They incorrectly joined one batch. Grouping and its unique index omitted the actual delivery date.

Applied migrations `20261027092738_batch_delivery_date_isolation` and `20261027092900_batch_delivery_date_index`, once each. The first replaces existing helper definitions and guards manual mixed-date creation/assignment. The second corrects the existing unique index and adds one necessary `delivery_batches.delivery_date` column. No new table, duplicate helper overload, additional trigger, historical backfill or cleanup. The first migration's initial verification exposed the old index restriction; the second closes that restriction. Both migrations are required in order.

Automatic groups now use campus, gate, delivery window and Africa/Lagos delivery date. Scheduled orders use `scheduled_for`; immediate orders use `created_at`, matching existing admission business-date semantics. An unknown scheduled date stays manual. Existing undated groups are reused only when their actual membership has the matching date; they then receive that date. Historical mixed-date groups are not silently reassigned.

Manual creation and staged assignment reject mixed dates. Existing manual reassign/split/cancel and order-before-batch locking remain. The admin batch list displays saved dates. The database helper functions retain service-only execution; frontend callers go through role-checked routes.

## Evidence

- Before correction: two scheduled delivery dates produced one batch.
- After correction: actual Test Two transactional SQL assertions pass for same-date grouping, future-date separation, stored dates, immediate orders without an ordering-window association, closed delivery-window fulfillment, Lagos midnight, replay stability, pending-payment refusal, unknown-date refusal, manual mixed-date refusal and no implicit rider authorization.
- Reusable test: `holy-grills-backend/tests/sql/batch_delivery_date_isolation.sql`. All fixtures are rolled back; no provider payment, email or push claims.
- Backend suite: 566 passed after merging user changes.
- Frontend TypeScript and changed-component ESLint passed.
- Existing security-advisor findings remain outside this batch. The three affected helpers are not publicly executable. All three affected helpers have one overload each, service-only execution, and the original two staging triggers remain. Five native admin browser regressions pass for staged assignment, create/retry, reassignment, split/retry and cancellation.

Still open in the larger launch audit: physical reward promise snapshots and handover, broader promo/payment/refund combinations, generalized multi-benefit campaigns, delivery exceptions/payouts, durable email/push worker proof, returning-user/storefront checks and the native Chrome installation-menu report. Cleanup remains paused.
