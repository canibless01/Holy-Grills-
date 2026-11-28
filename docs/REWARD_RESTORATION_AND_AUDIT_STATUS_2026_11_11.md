# Reward restoration and consolidated audit status — 11 November 2026

## Completed verification

Two additional production PostgreSQL matrices passed against current main `977db18`. Each creates isolated identities and configuration inside BEGIN/ROLLBACK. No existing customer identity is reused. A subsequent read found zero fixture users for either test prefix. No provider payment, refund or external notification was sent.

`holy-grills-backend/tests/sql/combined_benefit_restoration_rollback.sql` verifies a single checkout combining campaign free-side credits, delivery discount and reserved food-HP multiplier with a promo and an order-lock discount. Its ₦180 wallet debit receives a ₦30 partial refund, then a ₦150 remainder on customer cancellation. The partial refund retains the side consumption, promo use, used order lock and both attached campaign benefits. Cancelling before preparation restores each eligible benefit, preserves its original expiry and does not duplicate the campaign's already-earned 50 HP. Disabling the campaign between checkout and cancellation does not rewrite earned benefits. Original and different-key cancellation retries preserve the ₦180 total refund, side balance and promo quota.

`holy-grills-backend/tests/sql/menu_linked_reward_delivery_rollback.sql` verifies a physical food reward explicitly linked to a real menu item. It exercises HP redemption, zero-priced reward checkout with paid delivery, authenticated kitchen preparation/ready staging, batch assignment, unrelated-rider denial, assigned-rider visibility/pickup, successful delivery, attempted/unclaimed delivery, partial/full/replayed monetary refunds and early cancellation. Handed-over rewards remain consumed after a monetary refund; early cancellation releases the unused entitlement. Three redemptions spend 300 HP and three stock units; releasing an order claim does not create another stock unit or refund the original redemption HP. Wallet funds return exactly once.

Both matrices passed after their final edits. The targeted checkout quote, atomic refund route, order-lock policy and expiry-race suite passed **43 tests**. These cases found no new application defect; this commit adds reproducible coverage and consolidates status. No runtime or schema change was needed, so no new frontend build or migration is required for this batch.

This does not prove every reward type, independent-session race, interrupted handover or refund policy combination. Existing ambassador grant/restoration concurrency evidence remains in [the grant reliability record](AMBASSADOR_GRANT_RELIABILITY_2026_11_09.md).

## Operational reports

The reporting implementation and live configuration are consolidated in [the evening report record](EVENING_REPORT_SCHEDULE_2026_11_10.md). Daily reports run at **21:00 WAT**, covering the preceding 24 hours. The first report after the timing change was accepted by Resend at **21:30 WAT on 10 November**. Inbox receipt is awaiting the owner's check; provider acceptance is not inbox confirmation. Staff abandoned-cart alerts wait at least 30 minutes and recheck activity/payment before dispatch. The requested internal/test notes are removed from the email body.

## Remaining work, consolidated by priority

These are remaining coverage or feature gaps, not a claim that every item is broken. Older progress-log entries are historical; subsequent closure evidence takes precedence.

1. **Events — delegated to the other chat:** the owner requested no further event implementation here. A quick automated regression run passed 114 event tests; see [the follow-up checks](MENU_CRAWL_AND_SETTINGS_CHECK_2026_11_11.md). Historical exceptional recovery items in [event operations](EVENT_OPERATIONS_2026_11_10.md) remain for that chat to reconcile with its latest work; they are no longer this chat's next implementation task.
2. **Additional reward combinations:** wider squad/earned-reward, legacy and special reward variants, and interruptions during physical handover. The combined partial-refund/cancellation and menu-linked delivery cases above are now closed; generic physical delivery and ambassador last-use/restoration concurrency were already verified.
3. **Settings and permissions:** finish the remaining enabled settings/feature-flag consumer matrix, native staff/profile/campus action boundaries, and historical RPC/RLS/grant/schema-use review. Previously completed community-manager, wallet, event and stock boundaries should not be retested as though unimplemented.
4. **Reports and inventory:** remaining historical export/chart/refund arithmetic and populated stock reconciliation/export/low-stock notification cases, beyond completed wallet analytics and operational summaries.
5. **Other administration and presentation:** remaining newsletter/preferences, ambassador measurement/share/report exceptions, review/public-rating presentation and storefront editing/sorting variants not covered by existing evidence. Disabled marketplace/subscription and broader catering variants remain separate from enabled launch flows; automatic wallet funding is already implemented and is not that deferred subscription scope.

Real device installation/push/GPS and the ordinary customer ordering loop have owner confirmation. Do not reopen those as outstanding solely because older documents predate that confirmation. Inbox report receipt and any actual provider/bank settlement remain operational observations, separate from SQL rollback proof.

## 12 November follow-up

The [squad/recovery/reporting batch](REWARD_COMBINATIONS_AND_REFUND_REPORTING_2026_11_12.md) now closes the specified squad/earned physical reward/promo/lock/campaign combination and isolated delivery-financial recovery checks. Retained-revenue defects in the wider reports are fixed, including card-to-wallet refund attribution. The [delivery cushion pool](DELIVERY_CUSHION_POOL_2026_11_12.md) is also fully implemented and live. These later records supersede those particular open entries above; broader legacy interruption, stock/reporting and settings/permission coverage remains open.
