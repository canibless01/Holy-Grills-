# Ecosystem audit and fixes — progress

Project: Supabase **Test Two**. Status: **in progress**. This report describes verified batches so far; it is not a full ecosystem sign-off.

## Verified closed loops in this batch

- Actual admin UI creates and edits menu categories and items. Values are checked in API responses and customer pages. Category editing, activation, deactivation and cancellation work.
- Item availability can be turned off and on; hidden items remain manageable by staff and appear through customer search. Blank daily limits store unlimited values. Invalid prices are rejected without changing saved prices.
- Required protein choices and three sides are created through the admin UI. Repeated modifier saves preserve group/option IDs. Invalid modifier prices send no mutation. A customer selecting beef and all three sides sees the correct 2,050 unit price and modifier summary in the cart.
- Selected-item availability and HP actions and campus kitchen capacity are exercised through the UI, with API readback and temporary settings restored.
- Super admin creates a global category and meal without a campus. Students in both audit campuses can view and add it to a cart. Campus admin cannot edit the global catalogue. Campus-specific price, limit and availability times have an editor, remain isolated, reject invalid input and can return to catalogue defaults.
- Direct Supabase attacks using audit accounts reproduced cross-campus catalogue reads, foreign-campus cart insertion and modifier attachment. The corrected policies reject the writes with 403 and hide foreign-campus records. Test rows are removed by exact IDs.
- Mobile guests cannot bypass menu campus selection. Invalid or missing campus API requests fail. Campus categories load, modifiers are priced correctly, campus contact settings switch correctly, and guest carts remain separate and retained across campus changes.
- Floating WhatsApp code is removed. Contact page and footer use campus settings, with global fallback. There is no floating contact control.
- Concurrent duplicate checkout intents resolve to one order and one wallet debit. Distinct intents competing for the last delivery-window slot or stock unit admit one order. A retry after spending the exact wallet balance returns the original order.
- A new actual two-meal checkout saves preparation notes, beef and three side selections. Confirmation, customer detail, admin and kitchen tickets render them; side quantities reflect the meal quantity. The database records one 4,350-naira wallet debit. Customers can read their own selections and kitchen cannot forge selection snapshots. Actual kitchen buttons advance this order from received to preparing to ready; its ready ticket and choices survive reload.
- A simulated account-profile outage preserves sign-in credentials and provides a working recovery button.
- Actual scheduled checkout survives a lost committed response: retry resolves to the same order, one wallet debit, confirmation/share and confirmation reload.
- Refund and wallet-credit concurrency, independent equal-value intents, full-refund closure, cross-role denials and admin UI response-loss retries pass. See [migration/access verification](MIGRATION_ACCESS_VERIFICATION.md).

## Implemented changes that require further end-to-end verification

- Scheduling consent is retained, saved auto-scheduling uses backend window resolution, successful schedules navigate to confirmation, and copy reflects payment and preparation state. Browser response-loss passes; multi-tab UI checkout testing remains open.
- Preparation state is independent of payment state. Kitchen preparation requires paid orders; future scheduled orders are excluded until due. Cancellation and refund routes now use one atomic ledger/state transaction. Historical test-refund counters reconcile from real credits, partial refunds preserve preparation status, and retries do not repeat money. Kitchen/batch/rider/delivery and complete reward side-effect loops remain open.
- HP multiplier and flash reward release gates are off. Flash redemption enforces the release flag and campus in its database transaction. Automatic random event planning and advance notices remain to be completed and tested.
- Hero eyebrow is editable using existing banner metadata. The full storefront field, image, publication and customer-rendering matrix remains open.

## Validation

- Backend unit suite: **113 passed**, including modifier security and atomic refund-route regressions.
- Frontend typecheck and complete build pass, including routes, central message registry checks, value-text/settings checks, client/SSR builds and prerendering.
- Browser and direct API/database evidence is kept in the audit workspace. Private fixture passwords, sessions and funding manifests are excluded from this repository.
- New messages use the central `app/messages.py` registry and frontend `msg()` helper.

## Image architecture

Uploads remain **Cloudinary only**. The temporary Supabase Storage fallback is removed; its audit-only image and empty bucket were deleted. Cloudinary API key/secret are missing from the current audit runtime. The owner stored them in the personal vault; runtime binding and Cloudinary network access are still required; actual upload/display/replace/delete loops will be rerun afterward.

## Remaining full audit scope

Thirty-four ecosystem families and thirty-two admin sidebar sections have been inventoried. Discovery is separate from verification. Remaining work includes complete storefront/banner/media fields, promos and notifications, funding/provider boundaries, rewards/spins/fulfilment, order locks, kitchen/batches/riders/delivery, guests and tracking/QR, reviews, events/tickets, catering, marketplace, retention jobs, all feature flag consumers and role-specific UI gaps. Each needs UI input, stored values, cross-role results, failure/retry/concurrency and cleanup evidence.

The SQL definitions in this batch have already been applied to Test Two. Other environments must apply equivalent migrations together with the corresponding backend update. Publishing code to GitHub is separate from confirming a deployment is running it.
