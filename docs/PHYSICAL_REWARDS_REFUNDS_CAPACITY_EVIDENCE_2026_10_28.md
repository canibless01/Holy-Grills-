# Physical rewards, refunds, promos and capacity — 28 October 2026

## Implemented and verified

Admin refunds now require an explicit partial/full remaining-balance choice, positive amount and reason. Delivered orders additionally require acknowledgement. The API refuses omitted amounts and missing delivered acknowledgement. Customer cancellation retains its existing remaining-balance calculation. A delivered order can legitimately receive a refund; the change makes the decision explicit rather than silently defaulting to all remaining funds.

Real Test Two SQL (`tests/sql/physical_reward_delivery_refund.sql`) exercises HP redemption, paid delivery with a zero-price physical reward, authenticated kitchen preparation/ready staging, assignment, unrelated-rider isolation, assigned-rider pickup/delivery, attempted/unclaimed delivery, partial/full/replayed refunds, and early cancellation. Early cancellation releases an unused entitlement for reuse; a handed-over reward remains consumed after a monetary refund. All fixtures roll back. This verifies the generic physical entitlement path, not every menu-linked/legacy reward variant or actual provider payment.

Promo checkout now includes ambassador meal discounts in its total and records only the promo portion as promo usage. Atomic admission locks the promo and enforces current timing, campus, minimum, global and per-user limits. Partial refunds retain the promo use; full refund/cancellation releases it once. Historical cancelled uses no longer block reuse, and the existing counter reconciles on admission. Item/category restrictions now price only eligible server-priced food lines. Guest promo input is explicitly sign-in gated, matching authenticated promo validation instead of appearing to apply an ignored code.

Real `ambassador_checkout.sql` proves promo plus meal arithmetic, quota refusal without debit, early restoration, historical-counter recovery, partial/full refunds and no duplicate release. The multi-gift campaign checkout/refund SQL passes again after these changes.

## Capacity and date overrides

Daily kitchen slots limit one delivery date across ordering windows. Ordering-window slots impose an additional per-window ceiling. Delivery planning target is for rider grouping/time planning and does not admit or refuse checkout. Admin labels and an inline guide now distinguish these values.

A third order in the capacity-two test is refused for today without debit. Accepting tomorrow creates a paid scheduled order with one debit. Increasing capacity moves that paid order forward without charging again. SQL additionally verifies closed weekly windows reopened by a date override, closed overrides refusing admission, and an explicit dated ordering row taking priority.

Storefront hours for one date affect actual availability when there is no higher-priority explicit dated ordering window. Weekly operating hours now also inform the checkout fallback. Explicit dated ordering windows take priority, then the date override, then weekly ordering windows, then weekly operating hours, then environment defaults. The admin explains the precedence and does not imply an hours override increases capacity or moves existing orders. Saving a stored weekly day preserves its existing time fields.

## Role creation correction

The application recognized community_manager but the database role enum did not contain it. The enum is extended once; super-admin can assign the role through Admin Users. Real authenticated role assignment and campus/financial boundaries pass in `ambassador_role_boundaries.sql`. This closes a gap that earlier permission-only checks did not cover.

## Validation and migrations

Backend suite: 697 passed. Frontend typecheck and production build pass. Controlled React browser checks prove explicit partial/full/delivered refund review, remaining balance, separate retry intent keys, capacity terminology, community-manager selection, and weekly time preservation. Provider requests are controlled in these browser checks.

Seven ordered migrations (20261028095733 through 20261028101510) extend the existing enum and replace existing functions/trigger behavior. No table or column was added. Final inspection shows one 38-argument hg_create_order_atomic and one 6-argument hg_refund_order_atomic; anon/authenticated cannot execute either. The promo trigger helper is service-only. Migrations were applied to Test Two and are retained in order; follow-ups refine the same functions rather than introduce overloads.

Security advisors were reviewed. Existing findings remain for pg_net placement, RLS without a policy on newsletter_deliveries, other callable security-definer helpers and disabled leaked-password protection. These are not a clean all-database security sign-off. See https://supabase.com/docs/guides/database/database-linter and https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection .

No live provider charge/refund, push delivery, customer message, or production settings change was made by the rolled-back fixtures. Remaining provider/device cases, payout settlement, broader reward/stacking variants and the per-action role matrix remain tracked in LAUNCH_REMAINING_2026_10_28.md. Database cleanup remains paused.
