# Ambassador programme, signup and scheduling — 28 October 2026

Updated from main at 38da146 before edits. The user's ambassador programme and email branding changes are retained. Campaign/signup checkpoint already published at 2eaa837.

## Applied SQL and financial boundaries

Applied the four supplied ambassador migrations in order. Fixed the settings seed's text/jsonb mismatch and excluded inactive staff from the RLS actor lookup. Subsequent correction migrations replace existing functions; they do not create alternate reward/order engines or extra order RPC overloads. The programme has 12 distinct tables, all with RLS. Authenticated SELECT is granted under their ownership/campus policies; anonymous reads and authenticated direct writes are denied. All financial and tracking mutation RPCs remain service-only. Existing order RPC has one 38-argument signature. Search path on the new timestamp trigger is pinned.

Repaired during executed tests:

- Reward grant ledger and HP/free-side/meal benefit now commit atomically. Failure cannot strand an issued ledger row without its award. Retries resolve the same receipt; new intentional overrides include their terms in their intent identity.
- Meal-discount reservation is inside order admission, alongside wallet debit. Losing the final-use race rolls the new order back. Early cancellation restores the use inside the existing refund transaction; it preserves the original expiry.
- A later referral click cannot take an earlier delivered order. Attribution reads the qualifying historical click trail, self-clicks are refused, adoption replay does not increment counters, and delivered-order replay remains one attribution.
- Corrected the supplied attribution function's enum/empty-string comparison.
- Campus admins cannot patch other-campus or global milestones through the service client. Rule input validates booleans, whole-number counts, amounts and bounds. An automatically issued rule may use its still-authorized creator if no environment actor is configured. Pending auto claims can recover on later evaluation.
- A duplicate-grant response no longer checks the UI's additional-grant authorization box automatically.

The CLI could not generate files in this runtime: the current package required an unwritable home directory and older package installation failed. Correction filenames therefore use the actual UTC timestamp; SQL was applied through the connected Supabase migration tool. Applied corrections are kept in order for reproducibility, with no duplicate table/function signatures left behind.

## Signup and consent

Removed registration's local-import crash; missing fields get actionable messages before account creation. Academic-reference retry retains campus selection. Registration accepts /register and /signup; hosting routes are synchronized. Shared auth inputs and signup selects now have connected labels.

Terms and optional promotional emails use separate checkboxes. Marketing defaults off, without disabling transactional messages. The existing atomic notification-preferences function synchronizes the newsletter audience: opt-in/resubscription, retry without duplicate subscribers, and opt-out. Welcome/account and earned-gift notifications are not categorized as marketing.

## Scheduling

Replaced the contradictory 'no date to pick' / 'no bookable window' panel. The calendar displays 14 Lagos business dates, closed/full states, bookable windows and remaining capacity. Unavailable slots cannot be chosen. Selection is campus-bound and carried into checkout, even while today's kitchen is open. Checkout includes the chosen date/window; backend revalidates the exact window and current capacity before admission. Automatic next-available rollover remains available separately; a deliberate date choice is not silently replaced.

## Executed evidence

- Full backend suite: 683 passed.
- Real rolled-back Postgres scenario in tests/sql/ambassador_checkout.sql: HP, free-side and meal grants; HP replay; duplicate monthly grant; failed bundle leaves no partial HP; discounted wallet checkout; second final-use admission leaves no order/debit; early cancellation and retry restore one use; anonymous adoption replay; historical last-click attribution and self-click refusal.
- Real authenticated-role scenario in tests/sql/ambassador_role_boundaries.sql: student own read, denied direct write, campus-admin isolation, super-admin global read and inactive staff refusal.
- Real rolled-back consent scenario: opt-out → opt-in twice produces one active subscriber → opt-out removes it from the audience. No emails sent.
- Controlled HTTP browser: birthday omission blocks network; consent false/true payloads; reference retry; calendar full/unavailable/remaining states; selected date/campus persistence; all three new admin screens; milestone creation and reflected count. No remote campaign, milestone, signup or provider mutation from the browser.
- Ambassador sharing contract, TypeScript, central message registry, route configuration and production build checked.

No production campaign or ambassador rule was enabled, no payment/provider refund/blast was initiated, and test transactions roll back their fixtures. This evidence does not establish actual native sharing to WhatsApp, production push delivery, live Paystack methods or all browser/device behavior. Returning-browser content refresh and push prompt/subscription reports are the next active checks. Broad launch matrix remains in LAUNCH_EIGHT_AREA_STATUS_2026_10_27.md.
