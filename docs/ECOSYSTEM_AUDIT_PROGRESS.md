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
- Floating WhatsApp code and the permanent mobile contact strip are removed. Desktop navigation has no Contact Us item. Inline contact buttons in the account menu, FAQ and footer reveal campus WhatsApp and the global support email; legacy /contact URLs still work.
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
- Storefront text, slide, placement and publication loops below pass. Actual Cloudinary upload, decoded images and successful image-share export remain open because the attached runtime blocks Cloudinary outbound hosts.

## Validation

- Backend unit suite: **172 passed**, including modifier security, atomic refunds, feature gates, spin contracts, delivery-multiplier recovery, independent carousel configuration, contact scope and newsletter contracts.
- Frontend typecheck and complete build pass, including routes, central message registry checks, value-text/settings checks, client/SSR builds and prerendering.
- Browser and direct API/database evidence is kept in the audit workspace. Private fixture passwords, sessions and funding manifests are excluded from this repository.
- New messages use the central `app/messages.py` registry and frontend `msg()` helper.

## Image architecture

Uploads remain **Cloudinary only**. The temporary Supabase Storage fallback is removed; its audit-only image and empty bucket were deleted. Cloudinary credentials are configured privately for the audit backend; no credential fallback is committed. Its upload status and signer are checked, and pasted URLs must be images in the configured Cloudinary account. The running cloud environment still omits `api.cloudinary.com` and `res.cloudinary.com` from its enforced allowlist. Successful upload, decoded-image display, asset replacement/deletion and successful image-share export remain unverified until that policy is applied.

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

## Exclusive-spin award and fulfilment follow-up

- Controlled failures reproduced a consumed spin credit with a success response after the prize grant failed, and a physical prize saved without its campus. Credit consumption and prize issuance now commit in one service-only database transaction. A forced HP-ledger failure rolls back the credit, receipt and balance together.
- Admin prizes have explicit categories: HP, physical fulfilment, delivery-fee credit and next-delivery food-HP multiplier. Category values determine the effect; the label can change independently. Winning results snapshot the configured name, category and value, so a later pool edit cannot alter a saved result. Empty or unreadable pools supply no mock prizes.
- Actual admin create/edit touches name, relative weight, campus scope, availability and category/value fields. Campus admins cannot edit global prizes; super admin can create a global prize without a campus. Admin read failures have a recovery control. The obsolete extra-spin-cost control and unused static prize fallback are removed.
- Actual customer UI loses a committed HP-spin response, retries its persisted request ID, and shows the original 43-HP award. Six replays after changing the pool return that same result. One HP ledger row is recorded. Customer My Rewards shows saved prize status; actual campus-admin fulfilment of physical prizes reflects after customer reload.
- Six independent requests compete for one final credit: one succeeds and five return no-credit errors. A separate last-credit browser test loses the committed response, closes the wheel, reloads with zero credits and recovers the same saved result. Collecting it clears the pending request identity.
- Admin credit grants also save their request identity. Lost-response UI retry and six concurrent matching grant requests create one credit row. Repeating a grant after its credits are spent does not replenish them. Cross-campus admin grants are rejected. Global credit validity is now read from the same authoritative setting by the editor and the grant route; a temporary 36-day UI change produces a 36-day grant and is then restored.
- Email search had removed dots from addresses, preventing the grant form from finding a customer. Dots now survive the filter; actual and unit tests still enforce active-student and campus restrictions. Foreign-campus searches return zero results.
- Actual authenticated SQL cannot call the private spin function, replenish credits, forge a result snapshot or insert a fake prize receipt. Staff fulfilment retains column-limited updates and campus RLS. A committed receipt remains recoverable while the release flag is off; a new spin is rejected. Prize fulfilment retries preserve the first fulfilment timestamp and avoid repeating status notices.
- Rollback tests verify that delivery-fee and next-order-multiplier categories save their profile effects. Their later checkout consumption, cancellations, stacking and reward recovery still require the wider fulfilment audit. Physical prizes currently use the campus team's manual fulfilment pathway; automatic food attachment and delivery-choice integration remain open.

The spin migration reuses existing prize, credit, fulfilment, HP-ledger and monthly-tracker tables. It adds four used columns, one receipt business-key index and two private transaction functions; it adds no table. See the access verification document. Full ecosystem verification, external notifications and the deferred visual redesign remain in progress.

## Delivery HP multiplier failure/retry follow-up

- An isolated actual-profile test reproduced the pending multiplier changing from 2 to 1 when the primary payout RPC failed, with no HP award and no order created. The test restored the original profile value. The multiplier is now consumed inside the primary HP transaction, after the ledger award succeeds.
- The payout compares the multiplier used by the server's calculation with the locked profile value. A stale calculation returns a conflict without an award; the backend rereads it and recalculates. This prevents two simultaneous deliveries from both applying one bonus. An unavailable profile or payout leaves rewards pending instead of guessing away the bonus.
- Rolled-back database tests force the HP insert to fail and verify unchanged balance, multiplier and order marker. Subsequent success/replay produces one award. A second order's stale 2× calculation is rejected, then its recalculated 1× award succeeds. The two ledger awards total 306 HP and the monthly counter rises by the same amount. Replaying the first award preserves a newly granted 3× multiplier.
- The complete order HP amount, including the server's squad calculation, is saved in the payout transaction instead of a later separate update. Owner food HP also updates the existing monthly tracker atomically. Zero-food deliveries do not consume a food-earning multiplier.
- One private payout definition remains. The old five-argument definition is removed, and the seven-argument definition has defaults for the two added fields. Actual service-client calls using both legacy and current argument sets replay an already credited audit order successfully. No table, column or index is added.

These verify the primary payout and retry boundary. Real spin-multiplier-to-new-order browser delivery, auxiliary reward recovery, partial-refund HP rules, benefit stacking and delivery-credit checkout consumption remain under audit.


## Storefront, carousel and contact follow-up

The carousel editor now groups each slide's image, optional phone crop, eyebrow, title, subtitle and CTA label/destination together. Adding, editing, reordering and removing slides saves one versioned configuration in the existing `banners.metadata` JSON. The first slide is mirrored into legacy columns; older records retain their existing copy until edited. No new table or column is needed.

| Admin surface | Verified loop | Remaining limit |
| --- | --- | --- |
| Hero / homepage banners | Three independently configured images, eyebrows, titles, subtitles and CTA destinations; live dot navigation matches image position and copy; CTA opens the configured page; reorder/remove persist together | Actual Cloudinary image decode/upload blocked |
| Menu / checkout banners | Dedicated admin tabs; three independently configured slides appear only at their destination, with working navigation | Same media limit |
| What's Inside / How It's Made | Native image URL, title, subtitle, badge, CTA and individual eyebrow fields read back and render in their cards; dimensions allow clicks; public CTA destinations work for guests | Same media limit |
| Promos | Home, menu and checkout placements render their configured image URL and copy in the intended channel | Provider media bytes unverified |
| Testimonials / Our Story | Rating, name, review, image URL, story title/caption and CTA propagate; stored ratings are displayed; fabricated default reviews and images are removed | CMS testimonials are labelled feedback, without claiming verified orders |
| Tier Icons | All four native slot inputs save; campus-specific icons refresh their consumers and preserve global inheritance | Decoded artwork blocked |
| Early Supporters | Native name, note, social URL, order, activity and photo clearing persist; inactive entries remain manageable; customer visibility responds | Uploaded photo bytes blocked |
| Popup Flyer | Guest and signed-in campus copy/image URL/CTA; dismiss; once per visit and reset after login | Same media limit |
| Share Templates | All four slot editors save image URL and caption; resolver uses the intended slot then general fallback; actual order/referral share captions use real HP/code values | Image download failure offers Retry; successful rendered-image export blocked |
| Newsletter | Guest campus subscription → admin list → scoped staff unsubscribe; campaign subject/body → queue/view/cancel; signed public unsubscribe page requires an explicit click and supports replay | Provider preview now returns recoverable 503 instead of crashing; email delivery and worker execution remain unverified |
| Contact | Logged-in accounts from both test campuses hard-reload without campus selection and receive their own WhatsApp link plus global Gmail; guest inline options work; desktop header and fixed strip have no contact control | Outbound WhatsApp/email delivery is outside the local UI-link check |

Further failure checks verify a lost committed banner-create response recovers the same UUID and record, six simultaneous matching create requests return one 201 and five 200 responses, and conflicting intents return 409. Scheduled dates entered in Lagos time store UTC and remain hidden before publication. Stale image/copy edits return 409. Failed CMS reads show a working Retry and block editing instead of presenting an empty catalogue.

The carousel text animation no longer waits indefinitely on the outgoing title, and automatic advancement pauses during manual selection. Contact controls on static pages retain their open state while the authenticated campus finishes loading. Seed/example actions are removed from every storefront tab; empty sections remain empty. New editor/error messages use the central registry.

The existing FAQ Gmail address is now stored once in the global public `support_email` setting. WhatsApp for a resolved campus comes from that campus's configured public number; an absent campus number does not silently choose a different campus or global number.

Direct role checks and migration duplication/grants are recorded in [migration/access verification](MIGRATION_ACCESS_VERIFICATION.md). Temporary carousel and inactive global permission-probe rows are deleted by exact ID. Other synthetic CMS fixtures remain confined to the audit campus. This batch does not close the wider ecosystem families listed above.


## Delivery-credit and monthly-perk checkout follow-up

The audit reproduced two payment/benefit gaps: an earned spin delivery cap was not read at checkout, and the monthly helper could insert a usage claim while reporting failure. The former post-payment delivery-fee patch also did not recalculate the actual debit. Those paths are replaced with read-only pricing and an atomic admission claim.

- Checkout now shows the original delivery fee and separate squad, spin or monthly reductions; payment uses the same final total. Unavailable benefit reads block pricing rather than silently charging the full fee.
- Each new delivery-credit win keeps its own immutable cap and pending receipt. Editing the prize pool affects later wins. Checkout chooses the oldest eligible receipt, after preserving monthly full-delivery precedence and existing legacy caps. Zero-fee orders retain the credit.
- Receipt consumption, monthly usage, legacy-cap reset, order admission and wallet debit commit together. Stale claims request a fresh quote; failed payment rolls back consumption. Existing paid-order idempotency recovers the original admission.
- Pre-preparation cancellation restores the exact consumed benefit once. Later-preparation and partial-refund policies remain open. Automatic delivery credits cannot be fulfilled manually from the staff prize list; customer history distinguishes pending credits from credits applied to an order.
- Native testing uncovered secondary query ordering replacing the primary sort. The shared query builder now preserves both terms, so a UUID tie-breaker cannot displace chronological reward order. A regression test covers that behavior.
- Availability and next-slot capacity checks now count previously created scheduled orders on their scheduled Lagos date, rather than only counting records created today. Regression cases include the Lagos/UTC midnight boundary and future reservations.
- Capacity-rescheduling acceptance now survives a failed response and a normal checkout retry, matching the closed-kitchen path. New copy uses the central messages registry.

The backend suite has 179 passing tests. Rolled-back database proof covers debit/replay, cancellation restoration, insufficient-wallet rollback, monthly priority and independently snapshotted spin wins. Migration counts and execution/role restrictions are recorded in [MIGRATION_ACCESS_VERIFICATION.md](MIGRATION_ACCESS_VERIFICATION.md). This follow-up does not close multiplier stacking, free-side admission, physical reward attachment or broader Workstream A families.

Actual browser/API proof completes six cases: the admin creates a 100-cap prize, grants two spins, changes its cap to 200 between wins, and the customer retains both snapshots; manual credit fulfilment returns 409. Checkout combines the active 205 food discount with a 100 delivery credit, reducing the 250 fee to 150 and the total to 1,995. A committed response deliberately replaced with 503 is retried to the same order and confirmation page, with one wallet debit. Native cancellation restores the exact credit. Six distinct concurrent checkout intents produce one 201 and five 409 responses. Monthly full-delivery precedence leaves both spin receipts pending, then cancellation removes that monthly claim. All three financial test orders are cancelled with their ledger evidence retained; temporary prizes, grants and receipts are removed, and the referenced audit window is closed.

## Card checkout, payment recovery and unpaid fulfilment

This audit confirmed a wiring bug independent of Paystack test/live mode: meal checkout admitted a pending card order without initializing a provider payment, and confirmation/tracking offered no payment action. Order admission was therefore shown as success without a way to settle the card amount.

- Card and split checkout now open a saved-order payment section and initialize hosted Paystack checkout. Confirmation and tracking expose Pay and Check payment actions. A missing key/provider failure leaves a recoverable saved order. Guests use their order token; unrelated accounts and wrong tokens are denied.
- Pending confirmations say payment is required rather than celebrating confirmed payment. Returning from the provider triggers server verification; a callback query string cannot mark an order paid. Unpaid confirmations do not offer the paid-order share action.
- One stable order reference and the existing `payments` ledger preserve the hosted checkout URL for retry/reload. The provider receives the persisted card remainder, not the full split-order total. No frontend key, new ledger or source credential fallback is added.
- Verification checks successful provider transaction status, currency, amount, reference and order/user/campus metadata. Atomic confirmation serializes with cancellation, prevents reference reuse across orders, records one actual card receipt and leaves the kitchen status received. Replays do not repeat paid-order hooks.
- Failed webhook deliveries can be reclaimed with a compare-and-set retry. A currently processing duplicate returns 503 instead of falsely acknowledging completion. A processed replay remains idempotent. Existing processes abandoned in processing still require operational recovery.
- The existing database status trigger now rejects unpaid preparation/assignment/delivery, including direct Data API mutations. This complements the backend guard rather than relying on the UI. Payment ledger writes and the confirmation/status functions remain backend-only.

The full backend suite passes **195 tests**; frontend typecheck and complete build pass. Native browser proof uses a **controlled local provider fixture**, not the real Paystack sandbox: missing-key recovery, full-card checkout, abandoned return/reload/resume with one initialization, split wallet 500/card 1,800 for total 2,300, and guest payment/reload passed. Guest admission in that case was through the actual API; guest payment recovery used the native UI. Separate signed local HTTP tests reject bad signatures/wrong amounts, retry a failed event, race webhook with callback verification and replay six times, producing one paid payment row. Real kitchen API and authenticated Data API attempts cannot prepare the unpaid order.

All financial fixtures are synthetic audit actors. Test orders are cancelled; the guest's simulated receipt is explicitly voided without claiming a real provider refund. Simulated card funding returned to the audit wallet during test refunds is offset by a labelled cleanup debit, restoring its original 190,500 balance. No real provider charge was made.

Real Paystack authorization, provider webhook delivery, Cloudinary upload/decoded media and email/worker checks remain unverified. Their exact actions and expected results are listed separately in [PROVIDER_VERIFICATION_BLOCKERS.md](PROVIDER_VERIFICATION_BLOCKERS.md). [ADMIN_AUDIT_COVERAGE_STATUS.md](ADMIN_AUDIT_COVERAGE_STATUS.md) distinguishes inventory from verification and assigns every admin family to a workstream. Known functional gaps are kept separate from credential blockers; the full audit is not complete.

## Free-side rewards: admin grant to checkout, kitchen and cancellation

The audit reproduced an unsafe standalone consumer accepting an inactive foreign-campus item on an owned cancelled order. It also found checkout consumed free sides after admission/debit and swallowed failures, selection replacement could delete the old choice before validating the new one, and repeated admin grants had no durable retry identity. These paths now use the existing tables and status-log metadata, with no added table or column.

- Campus admins can manage their campus's free-side catalogue; super admins retain global controls. Item image URLs use the existing Cloudinary validator. Add/edit/toggle reads report failures, stale item edits conflict, and load errors offer Retry instead of presenting an empty catalogue.
- Admin grants have persisted UUID intents, bounded integer inputs and one atomic grant/audit entry. Retrying a committed grant does not add credits or refill already spent credits. The UI preserves the original validity in a pending request. Global validity edits affect new grants only; campus admins read the effective value.
- Checkout hydrates stored selections after reload, recovers an interrupted selection response and atomically replaces a choice. An invalid replacement leaves the old selection intact. Selected sides appear in the authoritative quote; stale item/credit/flag changes cannot silently remove a promised side while taking payment.
- The order transaction creates each zero-price side line, spends the exact eligible credit and removes the selection together with admission and wallet debit. Any failure rolls everything back. Order replay consumes nothing further. Kitchen/confirmation read the persisted side line.
- Pre-preparation cancellation restores the exact consumed credit once, retains its original expiry and refunds the wallet under the existing policy. It does not silently put the old side back in the cart. Later-preparation/partial-refund policies remain open.
- Free-side and spin grant notification templates are registered and link to Rewards. Transactional grant receipts are exempt from marketing throttling, which previously suppressed a second independent grant. Successful grant replay does not send another notice. Durable recovery after notification-provider/write failure remains part of the wider transport audit.

**Verification:** 205 backend tests pass; frontend typecheck, message-registry check and complete production/prerender build pass. Fifteen rolled-back live SQL assertions cover transactional failure, replay, replacement, scope and grant boundaries; migration/grant verification is in [MIGRATION_ACCESS_VERIFICATION.md](MIGRATION_ACCESS_VERIFICATION.md).

Eleven native browser/API cases pass: failed admin read/Retry; campus item creation/edit with Cloudinary URL mapping; super-admin validity edit/campus readback; a deliberately lost committed grant response plus six matching replays; one in-app receipt/deep link; lost selection response and reload; replacement and quote; lost paid-order response recovering the same checkout; kitchen side visibility; native scheduled cancellation restoring credit/wallet; and six independent competing checkouts yielding **one 201 and five 409** responses with one credit use. The test wallet returns to its original **190,500**. Exact test orders are cancelled, credits retired, owned side items deactivated and original global settings/ordering-window state restored. Financial/audit history is retained.

Cloudinary URL mapping is not proof of uploaded/decoded media; those bytes remain blocked by the applied runtime host list. Scheduled leaderboard/tier credit grants, queued HP multipliers, physical reward delivery choices and broader Workstream A families remain open. This batch does not mark the full ecosystem complete.

Seven additional actual browser/API permission assertions pass: native super-admin global item creation without a campus, campus-admin global read-only behavior, denied foreign-admin grant, denied student admin write, denied direct authenticated inserts into both credit and selection tables, and denied direct private-RPC execution. The exact global probe is deleted afterward.


## Workstream B draft integration checkpoint — 14 October 2026

See [Workstream B evidence matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md) and [selected test traces](WORKSTREAM_B_TEST_EVIDENCE.json). B is not complete. Six owned-domain migrations are live once each on Test Two; the matrix lists canonical SQL, checked grants/signatures and deployment dependencies. All exact owned synthetic fixture rows and eight Auth accounts were removed after deactivation/logout. No global release settings changed. Main at `723825e` was merged normally. Integrated backend regression: 209 tests pass; frontend typecheck/build checks recorded in matrix. Provider delivery, marketplace gated purchases, paid event recovery/refunds, broad onboarding/admin/reporting coverage and historical advisory closure remain open.


B continuation (14 October): free subscription retry/concurrency and last-code competition verified on a second isolated campus using campus-only gates; sold-out receipt retry and cross-listing intent conflict fixed and verified. Calendar consumer/browser save/reload verified; analytics read-failure interfaces and browser CSV escaping fixed. 212 backend tests, typecheck and complete build pass. Second exact fixture batch and campus overrides cleaned. No new live migration. See [matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md) and [requests to A](WORKSTREAM_A_DEPENDENCIES_FROM_B.md). B remains incomplete.

Integration with Workstream B's merged PR #66 preserves both registries and all platform routes/UI. The combined backend has **222 passing tests**; frontend typecheck and complete build pass. B's evidence remains scoped to its [evidence matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md), and its shared transport/HP/payment dependencies remain tracked in [WORKSTREAM_A_DEPENDENCIES_FROM_B.md](WORKSTREAM_A_DEPENDENCIES_FROM_B.md).
