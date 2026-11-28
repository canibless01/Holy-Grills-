# Checkout restart and rider handoff — 10 November 2026

## Customer checkout

A cancelled Paystack checkout left a campus/account-scoped checkpoint that blocked quoting and every subsequent checkout, even after the cart changed. The page now offers **Recover checkout** and **Start a new checkout**.

Starting again calls one owned-intent release endpoint. It does not initialize a payment or create a replacement order. A shared advisory lock and private closure receipt serialize release with in-flight creation, including an unknown/lost response. A late creation cannot revive a closed intent. Paid orders are returned for confirmation instead of being cancelled. Unpaid member orders use the existing atomic refund/restoration helper; only collected wallet money is returned, with no credit for an unpaid card allocation. Anonymous unpaid orders require the original scoped intent and matching contact proof; paid guest refunds are not introduced here.

After successful closure, the old checkpoint is removed, a new attempt nonce is persisted, guest receipt reuse is stopped, and the current cart is preserved. A failed/uncertain release keeps recovery available. Replaying closure cannot refund twice. Known cancelled/refunded results rotate the intent as well, allowing the same basket to be ordered again. A paid-race result clears the stale recovery pointer and opens the existing confirmation.

New checkpoints retain the originally submitted cart rows. Recovering an old order uses that snapshot, so a later callback cannot consume newly changed cart rows. Older checkpoints without snapshots preserve existing payment receipts rather than guessing which new rows were paid for. Existing verified late-payment reconciliation remains in place.

## Kitchen, admin and rider screens

- Kitchen queue and handoff responses include the persisted typed address, landmark/location and coordinates. Kitchen tickets and admin order cards show these details before assignment. A validated Google Maps link opens the saved pin without another geocoder request or API key.
- Handoff has batch checkboxes, select-all and one rider selector for the selected batches. Each zone remains a separate batch. Existing server authorization/payment/status checks run for each assignment. Successful assignments remain saved; failed rows stay selected with zone-specific error details for retry. A synchronous guard prevents double submission and scope changes stop the remaining loop.
- The rider API already returned all active batches, while the screen rendered only its first legacy `batch`. The screen now renders every returned zone and its orders together. All batch orders receive the same customer/address/item normalization. Pickup targets the selected zone; finishing one zone is no longer required to see the next. New-order sound detection also includes the other zones. Individual delivery confirmation remains per order.

## Verification

- Full merged backend suite: **1,529 passing tests**. Typecheck and full client/SSR/prerender build pass.
- Seven native mobile browser cases cover member/guest restart without a new order/payment call, failed release preserving recovery, paid-race confirmation, both rider zones visible, pickup of the second zone while the first stays pending, partial bulk assignment/retry, and kitchen/admin address/pin visibility.
- Production SQL fixtures execute in `BEGIN/ROLLBACK`: wrong-owner/guest denial, unknown-intent closure and delayed-create rejection, exact split-wallet restoration, no refund of unpaid card money, replay conservation, paid-order protection and service-only grants. No retained `audit-ca-*` accounts or real customer changes.
- Independent local sessions run the actual creation guard against a concurrent intent closure: the delayed creation waits, sees the committed closure and creates neither an order nor a debit.
- Security-advisor categories remain unchanged (2/1/13/22/1). No new scheduled service, provider credential or frontend environment variable is required.

Production migration history matches `20261110194546_release_abandoned_checkout_intents.sql` and `20261110194615_validate_guest_checkout_release.sql`. The second migration removes an invalid historical-column assumption caught by the rollback matrix before the new route was deployed; both applied definitions are retained in source history.
