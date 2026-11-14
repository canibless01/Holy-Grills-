# Earned reward promises — 27 October 2026

## Completed correction

Previously, checkout and redemption history consulted the latest reward catalog. Editing its name, image or linked menu item could silently change an already-earned entitlement. New normal and flash redemptions now capture public display/fulfillment details on the existing `reward_redemptions` record, inside the HP-debit transaction. Checkout, order admission and customer/admin history use that earned definition. Current menu availability still applies: unavailable original dishes remain owed rather than being silently replaced.

Migration `20261027095922_preserve_earned_reward_promises` adds one used JSON column and one invoker trigger helper, and replaces the existing 38-argument order function without changing its signature or grants. No new table or policy. The trigger overwrites submitted snapshots on INSERT and refuses subsequent snapshot, identity, campus or HP-cost changes. It does not automatically approve a redemption or debit HP; existing normal/flash debit RPCs remain responsible for those actions. Private catalog costing fields are excluded.

Claiming/releasing an order, selecting instant/next-order delivery and updating fulfillment status remain allowed. History shows the saved name/image/type and actual HP cost. Successful redemption reports the transaction's HP cost rather than the earlier catalog read; a failed post-commit display lookup cannot turn success into a retry instruction.

Legacy rows retain null snapshots. Their existing catalog fallback is preserved because the original earned definition cannot be reconstructed reliably. No historical values were invented or bulk rewritten.

## Evidence

Actual Test Two transaction, entirely rolled back:

- Used an isolated existing audit student; no new account or real customer data changes persisted.
- Normal redemption spent 100 HP; flash redemption spent 50 HP and both captured the same public promise.
- Catalog rename, repricing and deactivation did not alter either earned promise.
- Attempts to replace the snapshot or HP-cost receipt were refused.
- A zero-value order attached the original earned meal after the catalog change, with its original name and no charge/food HP on that reward line.
- Releasing its attachment preserved the saved definition. Final HP balance conserved both debits.
- Reusable SQL: `holy-grills-backend/tests/sql/earned_reward_promises.sql`.

Unit regressions cover changed/missing catalogs, unavailable original dishes, malformed snapshots, history display and post-commit lookup failure. Database inspection confirms one snapshot column, one promise trigger, the single existing order-function signature and service-only execution of the affected helpers. Security advisors add no finding for the invoker helper; unrelated historical findings remain open.

This closes catalog-edit drift and the tested redemption-to-order claim, not the whole physical reward handover/refund matrix. Multi-benefit signup/first-order campaigns remain open; no partial campaign editor was released.
