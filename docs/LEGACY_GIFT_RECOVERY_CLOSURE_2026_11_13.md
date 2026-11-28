# Legacy gift/reward recovery — 13 November 2026

## Current production exposure

Read-only inspection found **zero** legacy hot-dog gift rows, orders flagged with a legacy gift, legacy gift order lines, profiles holding an old next-order HP multiplier, profiles holding an old delivery cap, or redemptions missing an earned snapshot. There is no existing customer entitlement in this class to backfill or repair. `first_order_gift_enabled` is false; the old launch end is 5 August 2026. Both settings were left unchanged.

## Verification

- **39 focused backend tests passed**, covering disabled/expired/malformed legacy launch gates, unavailable settings failing closed, earned multiplier delivery recovery, payout interruption/replay and reward display/checkout boundaries.
- Fresh production `legacy_order_benefits_rollback.sql` passed legacy delivery-cap consumption and HP conversion into a durable attached entitlement; transaction interruption; lost-response retries after newer gifts arrive; cancellation preserving both the old captured multiplier and newer profile gifts; repeated cancellation conserving wallet/credit amounts; and explicit refusal of changed reward terms. All identities/configuration/orders were isolated and rolled back.
- Fresh production `earned_reward_promises.sql` passed normal/flash earned snapshots, later edited/deactivated catalogue data, immutable captured definitions/prices, attached-order release and HP conservation. The test now creates its own isolated account and real ledger seed instead of borrowing an existing audit account. All effects rolled back.

No application defect was reproduced in the supported legacy-credit paths. This closure adds reproducible coverage and evidence; no application/schema change, real charge/refund, external notification or speculative customer-data repair was needed.

## Closure boundary

The legacy recovery item is closed for the current launch configuration. Modern earned gifts/rewards retain their existing supported workflows. The disabled hot-dog promotion itself is deferred: its old implementation grants after delivery and performs separate writes, so these checks do not certify turning that obsolete workflow back on. Reintroducing it would be separate feature work, not recovery of any existing customer's missing gift. Historical database-permission review and operational inbox/nightly-job observations remain separate audit items. Admin page-by-page work remains with the other auditor.
