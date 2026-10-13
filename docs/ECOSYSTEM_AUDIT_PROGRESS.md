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
- Admin creates a delivery batch and assigns the ready test order through the UI. The assigned rider reads its choices, confirms pickup and delivery; the batch completes. The HP ledger records 205 food HP and 50 welcome HP, with no pending primary delivery award.
- Kitchen delivery/assignment bypasses are rejected in both API and direct database writes. Direct preparation of an unpaid order is rejected. Financial exits require the atomic cancellation/refund action. Bulk kitchen advancement is limited to paid, due preparation work.
- The delivered-order review completes the customer/admin/menu loop. Overall 4, kitchen 3 and rider 2 ratings persist; the menu shows one review. A lost committed response replays successfully. Six concurrent retries add no HP or monthly allowance usage. One actual 20-HP pending transaction is recorded; reload shows the saved review and removes the submission button. Invalid ratings, foreign owners and untrusted image URLs are rejected.
- A simulated account-profile outage preserves sign-in credentials and provides a working recovery button.
- Actual scheduled checkout survives a lost committed response: retry resolves to the same order, one wallet debit, confirmation/share and confirmation reload.
- Refund and wallet-credit concurrency, independent equal-value intents, full-refund closure, cross-role denials and admin UI response-loss retries pass. See [migration/access verification](MIGRATION_ACCESS_VERIFICATION.md).

## Implemented changes that require further end-to-end verification

- Scheduling consent is retained, saved auto-scheduling uses backend window resolution, successful schedules navigate to confirmation, and copy reflects payment and preparation state. Browser response-loss passes; multi-tab UI checkout testing remains open.
- Preparation state is independent of payment state. Kitchen preparation requires paid orders; future scheduled orders are excluded until due. Cancellation and refund routes now use one atomic ledger/state transaction. Historical test-refund counters reconcile from real credits, partial refunds preserve preparation status, and retries do not repeat money. Kitchen/batch/rider/delivery and complete reward side-effect loops remain open.
- HP multiplier and flash reward release gates are off. Flash redemption enforces the release flag and campus in its database transaction. Automatic random event planning and advance notices remain to be completed and tested.
- Hero eyebrow is editable using existing banner metadata. The full storefront field, image, publication and customer-rendering matrix remains open.

## Validation

- Backend unit suite: **137 passed**, including modifier security, atomic refund-route regressions, feature-gate errors and safe flag creation/retries.
- Frontend typecheck and complete build pass, including routes, central message registry checks, value-text/settings checks, client/SSR builds and prerendering.
- Browser and direct API/database evidence is kept in the audit workspace. Private fixture passwords, sessions and funding manifests are excluded from this repository.
- New messages use the central `app/messages.py` registry and frontend `msg()` helper.

## Image architecture

Uploads remain **Cloudinary only**. The temporary Supabase Storage fallback is removed; its audit-only image and empty bucket were deleted. Cloudinary API key/secret are missing from the current audit runtime. The owner stored them in the personal vault; runtime binding and Cloudinary network access are still required; actual upload/display/replace/delete loops will be rerun afterward.

## Remaining full audit scope

Thirty-four ecosystem families and thirty-two admin sidebar sections have been inventoried. Discovery is separate from verification. Remaining work includes complete storefront/banner/media fields, promos and notifications, funding/provider boundaries, rewards/spins/fulfilment, lock reminders and broader fulfilment/recovery cases, guests and tracking/QR, reviews, events/tickets, catering, marketplace, retention jobs, all feature flag consumers and role-specific UI gaps. Each needs UI input, stored values, cross-role results, failure/retry/concurrency and cleanup evidence.

The SQL definitions in this batch have already been applied to Test Two. Other environments must apply equivalent migrations together with the corresponding backend update. Publishing code to GitHub is separate from confirming a deployment is running it.

## Checkout pricing and order-lock follow-up

- A lock discount was being applied twice: a 2,095-naira debit accompanied a 1,890-naira stored total. The corrected transaction applies the 205-naira discount once. The server quote drives checkout total, discounts and food HP; a price change requires review before submission. Invalid quantities, payment methods and unknown delivery locations are rejected. Unreadable delivery fees or saved addresses cannot silently become free delivery.
- Actual Playwright quote failure blocks checkout; Retry total restores the verified 2,300-naira total and 102 food HP. Guest quotes report no earned HP. Quote API tests leave order count and wallet balance unchanged.
- Actual discounted checkout loses its committed response, then retries the same intent. It records one 2,095-naira debit, a 205-naira discount and a 2,095-naira stored total. Confirmation/share survive reload. Customer UI cancellation records one equal refund and restores the lock. The temporary audit lock date is restored.
- Customer UI exercises discount and HP selection, seven-day rescheduling and cancellation; admin date/status filters display the stored target date and reward. Six concurrent creates admit one lock; six reschedule retries spend one reschedule; concurrent cancellations are idempotent. Foreign-owner operations fail and campus admin/super-admin reads have the expected scopes. Own expired locks stop blocking creation even when the worker is offline.
- Direct authenticated lock date/counter editing was reproduced and is now denied. Validated backend writes condition on owner and active state, plus the expected reschedule counter. Calendar limits use the Lagos business day. Worker expiry cannot overwrite a concurrently used or rescheduled lock.
- A rollback-only transaction reproduced a refunded/cancelled HP lock leaving 100 spendable HP. HP locks now reserve their bonus at checkout and credit it in the existing order-update transaction at delivery. Rollback-only tests verify zero bonus after cancellation and one 100-HP ledger row after the valid preparation/assignment/delivery sequence, including a repeated delivered-order update. Legacy credited locks replay their existing ledger business key. A real browser HP-lock delivery, reminder/provider delivery and other reward recovery cases remain open.

These changes replace existing function signatures and reuse existing tables and indexes. See the access verification document for grants, migration counts and the remaining advisor notices. The full ecosystem audit is still in progress.

## Feature-flag controls and recovery follow-up

- Campus admins can read global flags; only active super admins can change them. Admin read failures show an error and working Retry rather than an empty catalogue. Descriptions entered in the create form are displayed from the stored row.
- Canonical release gates fail closed when their read fails. Changes refresh already-open user screens on focus and at a shared polling interval. Legacy UI aliases cannot override an off backend release flag. Marketplace navigation and trade controls, HP transfer, free sides, exclusive spin and Hall of Fame respond to their respective gates.
- Actual browser toggles hide/re-enable the HP transfer control and the three reward sections without reloading the page. Their write/read APIs return 403 while disabled. Tests restore all flags to their original values. HP multiplier and flash reward release flags remain off.
- A lost committed flag-create response is retried successfully in the actual admin UI. Six concurrent matching retries return the same record without changing its timestamp. A conflicting create returns 409 without overwriting it; invalid typed fields and a campus-specific flag request are rejected. Exact audit flag rows are removed.
- A deactivated super admin's existing JWT could previously update the flags table. The existing policy now uses the active-profile helper. A rolled-back database test returns zero updated rows for that actor and a campus admin, and one for an active super admin. Public flag reads remain available; authenticated TRUNCATE and anonymous writes are denied.
- The leaderboard now uses actual unexpired spin credits instead of promising a spin merely because today's displayed rank is in the top ten. A browser test with rank one and zero actual credits displays no earned spin. Spin award/fulfilment transactions and other feature consumers remain under audit.
- Two identical historical profile-protection triggers were found. The redundant one is removed, retaining the canonical enabled guard. Rolled-back authenticated writes still allow a normal own-profile edit and reject HP balance, wallet balance and super-admin role forgery. No function definition or role grants change in this cleanup.

New editor and error copy lives in `app/messages.py`. These migrations add no tables, columns or function overloads. This verifies the listed controls and boundaries; the full audit scope above remains open.
