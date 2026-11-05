# Paid event-ticket refunds

The owner selected these rules: **members receive wallet refunds; guests receive refunds to their original payment method; refunds are allowed only before check-in.** The implemented action refunds the entire ticket, including returning any HP spent on it. Partial ticket refunds and refunds after attendance are not offered.

## Admin flow

Events → Registrants → **Refund ticket**. The confirmation shows the ticket cash amount, spent HP and destination and requires a reason. The server computes the amount; the browser cannot choose one. Checked-in tickets have no action, and the transaction rechecks attendance before doing any financial work.

Events → **Refunds** shows the latest 200 records for that event, including processing, completed, failed and uncertain results. Opening and refreshing this panel is on demand. The page discards old responses and closes financial dialogs when campus scope changes. A failed response reuses the same request UUID until the admin changes the intent.

- **Member:** confirmed ticket cash (wallet plus captured card portion) is credited to the member's Holy Grills wallet; spent HP is returned as an adjustment, not new earned HP. The ticket, tier seat, promo use, discount-cost accounting and refund/audit receipt commit together. No provider refund is also created.
- **Guest:** the ticket is cancelled and a durable Paystack refund is queued. Its state remains `refund_pending` until Paystack reports `processed`; `pending` is never presented as completed. A locally rendered branded email receipt is queued only after processing is verified.

Amounts are the ticket's recorded cash price after discounts, not an invented credit for an unpaid portion or additional gateway fees. The original charge remains recorded. Repeated requests, even with a different request UUID, return the ticket's single existing refund instead of another payout.

## Recovery and provider checks

An immediate background wake handles normal requests; the existing scheduled-blast job recovers lost wakes. It scans at most ten due refunds within a 40-second start budget, with safe polling backoff. New requests and wallet notices take priority over old bank-processing polls. No new hosting service, Celery beat entry or credential is needed.

A guest POST verifies the original Paystack charge and uses a stable `hgticket_<request UUID>` refund reference supported by the [Paystack Refund API](https://paystack.com/docs/api/refund/). That money POST bypasses the generic retry decorator. A timeout after handoff without a usable provider ID becomes **uncertain**, not another POST. If a verified provider ID is known but saving the receipt is interrupted, recovery retains that ID for safe GET polling. Receipt checks compare original transaction ID, transaction reference where returned, refund ID, amount and NGN currency.

The admin can review an uncertain/failed guest refund using provider-log evidence:

- Supply an existing Paystack refund ID. The server queues a lookup and verifies it; the admin's assertion alone cannot mark money returned.
- Confirm that Paystack created no refund and queue another attempt. This is available only before a provider refund ID exists, and retains the same stable refund reference.

`failed` and `needs-attention` provider results require review. Bank details for Paystack's needs-attention flow must be handled through Paystack; this application does not collect them. In-app refund records do not import or automatically reconcile unrelated out-of-band refunds made in the provider dashboard.

Member notices have deterministic per-refund/channel IDs and are acknowledged only after their saved notification attempt succeeds. The existing email/push outbox handles external dispatch uncertainty. A duplicate webhook for the original charge after refund does not re-confirm the ticket or resend its QR; a different charge is still flagged for payment support.

## Database and authorization

Applied migrations:

- `20261105225852_paid_event_ticket_refunds.sql`
- `20261105230200_prioritize_new_ticket_refunds.sql`

Refund receipts/leases live in `hg_internal.event_ticket_refunds`, outside the public Data API, with RLS and service-role access only. Public functions are security-invoker and service-only; they revalidate active admin/super-admin identity and campus scope. Direct client writes to ticket ownership, amounts, payment/attendance status and refund data are denied. Limited old-API metadata/reference updates remain permitted through existing RLS during rolling deployment; these cannot forge a paid ticket or private refund.

Admission now locks its event before profile/ticket work, serializing it with refund/registration so a refund and entry cannot both pass their transaction checks. The tests verify atomic states and replay; independent concurrent database sessions and deliberately killed production processes were not exercised.

## Executed verification

The new native rollback matrix covers member wallet/card/HP/promo refunds, wallet-only and HP-only tickets, subsidy-cost restoration, transaction interruption, repeated requests, own/foreign/student roles, post-check-in denial, guest pre-handoff recovery, unknown handoff, provider review/replay, stale tokens, processing/completion distinctions, queued email, polling backoff and queue priority. The expiry matrix additionally verifies reversal of a reserved event subsidy, preserving its old value in the expiry receipt.

Mobile and desktop browser checks use the actual admin component with controlled local API responses. They passed required reasons, hidden checked-in actions, stable response-loss request IDs, server-owned amounts, provider evidence and refreshed result rendering, with no page errors or production writes. Full frontend build and TypeScript checks passed. Security advisors retain the same five pre-existing categories/39 findings, with no new finding.

No real customer payment, wallet credit or gateway refund was executed by verification. All database fixtures rolled back; zero audit users/refund records remained afterward. A real bank refund receipt remains operational acceptance, separate from these deterministic checks.

Release verification: **1,206 backend tests passed**, all **36** current SQL rollback scripts passed, both native browser variants passed, and the complete frontend client/SSR/prerender build passed. Production REST access to the private-table recovery RPC was verified read-only; its queue was empty.
