# Guest checkout email reminders — 12 November 2026

Guests who create an unpaid checkout now participate in the existing abandoned-cart reminder scan. The email address comes from that persisted guest checkout. Merely browsing, or entering an email in an unsubmitted browser form, does not create a reminder recipient.

The existing `abandoned_cart_nudge` flag and private per-campus `campus_cart_recovery` timing setting govern both flows. Guest reminders enforce at least 30 minutes of inactivity, repeat according to the configured interval (default 1,440 minutes), and stop within 48 hours or at the applicable ordering/preparation cutoff from the shared ordering calendar. The original scheduled delivery date is respected. The existing ten-minute scan and durable notification recovery worker are reused; no new beat service or per-guest recurring job is added.

## Behavior

- A guest receives email without an account or push subscription. No fake profile, newsletter subscription or in-app/push notification is created.
- The message says checkout is awaiting payment, not that an order is confirmed. Its Continue checkout link uses the full order UUID and private guest token, opening the existing tracking/detail/payment flow.
- Payment, cancellation, recovery, changed guest contact/ownership, a newer pending checkout, expired eligibility, a disabled feature or opt-out prevents sending. Eligibility is checked again at the database handoff boundary after preparation.
- Same-cart capture retries produce one saved email step; independent captures serialize. A separate recipient/campus throttle prevents repeated new checkouts from producing a burst. Missed reminder steps are not replayed together.
- Existing matching account email/promotion preferences and newsletter unsubscribe state are respected. A signed, opaque delivery-ID link lets guests stop future checkout reminders for that campus. GET shows confirmation without a write; POST performs the opt-out. Receipts and operational order updates are unaffected.
- Guest email uses the existing quota/provider router with marketing semantics. Standard unsubscribe headers select Resend initially; the existing OneSignal fallback retains its opt-out handling. This is not a new unlimited email allowance.
- The existing admin cart panel can search guest email/phone and queue an eligible guest reminder. It displays saved reminders separately from provider-accepted emails. Queued is not described as sent. Campus authorization remains enforced before the service capture.

## Database and verification

Migration `20261112125827_guest_checkout_email_recovery.sql` adds private, RLS-protected opt-out storage, guest-specific service-only lookup/capture/handoff/unsubscribe functions, lookup indexes and guest-aware recovery metrics. It does not update existing prices, orders, wallets or funding plans. The migration and diff were shown before applying; filename matches production migration history.

Production BEGIN/ROLLBACK tests pass guest discovery/capture, replay, worker lease exclusion, payment after capture, unsubscribe during queue wait, thirty-minute delay, preparation deadline, cancellation, recipient/contact proof, recipient throttling, missed-step behavior, 48-hour expiry, truthful counters and browser-role denial. A follow-up count found no audit guest campus fixtures. Local independent sessions additionally prove that a lost precommit connection leaves no phantom step, a competing capture succeeds, and exactly one durable email remains. The local metadata mirror is not a substitute for production RLS/foreign-key checks; its citext schema alias and missing delivery unique index were supplied locally only.

Full backend regression: **1,568 passed**. The first run exposed an existing test fixture fixed to an already-past November expiry; that fixture now uses a future relative expiry, without changing production discount behavior. TypeScript and the complete frontend build pass. All six native admin cases passed: mobile/desktop operational settings, member contact/counters, guest-email search/manual queue with accepted-count remaining zero, delivery-status read failure and cart read failure. These browser requests use controlled HTTP fixtures and make no production writes. Security advisors retain the same five pre-existing categories.

Tests do not send customer email or initiate a payment. Actual provider acceptance and inbox delivery remain separate from rollback/controlled-transport proof. The normal production scan may deliver legitimate eligible reminders after rollout.
