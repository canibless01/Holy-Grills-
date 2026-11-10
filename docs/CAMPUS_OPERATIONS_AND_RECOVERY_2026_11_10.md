# Campus operations and cart recovery — 10 November 2026

FUTA's explicit recipient is **grillthevibe@gmail.com**. In Admin → System Settings, `campus_operations_email` has a native recipient/switch/delay form and recent send states. Up to five private campus recipients; no automatic mailing of every campus admin. The real campus slug is `futa-main`; the follow-up configuration migration records that identity without hardcoding a UUID.

- Paid-order intent commits with successful payment. Operator mail includes contact phone/email, items/extras, amount and saved delivery address. Unpaid checkouts do not generate paid-order alerts.
- Staff cart alerts default to ten minutes inactivity, checked on the existing ten-minute cart task. Member carts and guest unpaid checkouts are captured. Alerts deduplicate per episode/recipient and are cancelled when no longer relevant. A location/final total is shown when checkout supplied it; earlier carts do not invent either.
- Daily mail covers the previous completed WAT day; weekly mail covers the previous Monday–Sunday. Counts: signups, paid orders/value/refunds on those orders, wallet funding, confirmed new automatic setups/automatic funds, event admissions, marketplace purchases, abandoned and paid-recovered carts. No visitor figure is invented; there is no complete site-visitor metric. Digests have core figures, without customer contact lists. Seven-day daily catch-up is bounded; persisted mail intents survive worker restarts.
- Recipient changes and switches are rechecked before dispatch. Claims are exclusive. A crashed read/preparation can be reclaimed; an uncertain provider handoff is held for review, never blindly resent. `Provider accepted` does not assert inbox delivery. Proven-unsent failures can be retried through the scoped admin endpoint; accepted/uncertain rows cannot.

## Customer reminder sequence

Investigation found the old code ran hourly, checked a 24-hour gap, omitted email from the cart channel set, had no 48-hour/preparation stop, and incremented attempts even when no notification was saved. Live settings/campaigns had no alternate implemented cart sequence. A prior count of 27 attempts therefore was not proof of 27 delivered notices.

`campus_cart_recovery` is private and editable: first delay **30 minutes**, repeat **1,440 minutes**, maximum **48 hours**. This is the stated default pending clarification of “every thirty”; the interval can be changed to 30 minutes without code. Preparation uses the existing ordering calendar, dated overrides, Sunday closures and the scheduled order's delivery date, rather than a hardcoded 16:00. Recovery stops at payment, cleared/changed cart, deadline or maximum age. No missed-step burst.

A due step and email/inbox/push records commit atomically through the existing notification outbox. Push-disabled members still get email plus inbox, when email/promotion preferences permit. Delivery rechecks preferences, cart ownership/activity, payment and deadline. Customer push permissions are not required for email. Guest unpaid checkouts generate staff recovery alerts; this change does not manufacture an authenticated notification profile for guests.

The cart screen distinguishes **saved reminders**, email provider acceptance and push provider acceptance. Historical attempt counts are not labelled as delivered notices. Manual reminders share the same due-step admission; they cannot bypass the cadence or stop rules.

## Super-admin customer tests

Super-admin-owned orders receive a server-derived sticky `is_test` flag, including existing orders and later role promotions. Other staff editing a real customer's order does not make it a test. Tests are excluded from operational/admin order queues, ready staging, real capacity/item/promo counts, customer-report views and operator emails. Test delivery hooks do not award real referral/squad/ambassador effects. Wallet and HP transfers cannot move test credit into a real customer's account. The owner's wallet/test ledger is retained. Own order detail identifies a test order.

Reporting views preserve underlying RLS with `security_invoker=true` and read-only grants; guest orders remain included. Catalog/CMS management performed by a super-admin stays real. This isolates test **orders and reporting**, not a payment-provider sandbox or every future global stock/event simulation.

## Verification

- 1,481 backend tests pass before merging the independent event-operations work; typecheck and full client/SSR/prerender build pass.
- Five native browser cases pass: mobile/desktop recipient/toggle save, cart phone/WhatsApp and truthful counters, status error and cart failure without fabricated emptiness. Mobile screenshot inspected.
- Fresh production SQL matrix passes in `BEGIN/ROLLBACK`: owner-derived flag, guests, paid-only capture, actual email/inbox/outbox rows with push disabled, dedupe/stops, report totals, exclusive claims, interrupted handoff and removed recipients. All `audit-ops-*` accounts roll back; no customer/provider messages are sent by tests.
- Independent local sessions prove a process rollback releases the cart lock, only one email/inbox step commits and committed-response replay creates no duplicate.
- Security-advisor category counts remain 2/1/13/22/1, unchanged from baseline. No new recurring service, card charge or wallet balance reset.
