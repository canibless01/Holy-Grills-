# Payment amount reconciliation

One question decides every provider webhook: **does the amount that was actually charged
match the amount we asked for?** It is now answered in exactly one place —
`app/services/payment_amounts.py::validate_charge_amount` — and every payment type uses it
(orders, wallet top-ups, event tickets, marketplace purchases, HP bundles).

## Why this exists

Paystack settles a card charge **plus its gateway fee** whenever the customer bears the fee
(the default on the hosted checkout). So a ₦3,000 ticket can arrive as `amount = 315000`
kobo with `fees = 15000`.

Orders and wallet top-ups always allowed for that (`validate_paystack_amount`). Event
tickets, marketplace purchases and HP bundles compared the gross amount with
`abs(paid - expected) > 0.01`, so:

1. Paystack took the money and emailed the customer a receipt;
2. we answered the webhook with **500 + `Amount mismatch`**;
3. the ticket/purchase stayed `pending` — charged, but the registrant was missing from the
   admin list and from the "send registrants to host" email, even though the seat had
   already been counted;
4. the failure row was written with `campus_id = NULL`, and the admin webhook log is
   campus-scoped, so the failed delivery was invisible to every campus admin.

## Accepted charges

`validate_charge_amount(data, expected_naira, provider, label=...)` accepts, in order:

| # | Condition | Meaning |
|---|-----------|---------|
| 1 | `paid == expected` | merchant bears the fee |
| 2 | `paid - fees == expected` | customer bears the fee |
| 3 | `requested_amount == expected` | provider echoes what we initialized |
| 4 | fees absent, `expected <= paid <= expected + max(₦150, 2%)` | accepted, flagged `source: tolerance` (re-read via `/transaction/verify`) |

Anything else raises `ChargeAmountError`. A genuinely wrong amount is still refused — this
is a fee allowance, not "accept whatever arrived".

Amounts must always come from **our** record (`event_tickets.card_amount_used`,
`orders.card_amount_used`, `expected_amount_kobo` in the payment metadata), never from the
client or from the provider's gross amount.

## Where the expected amount lives

| Payment | Source of truth |
|---------|-----------------|
| Order | `orders.card_amount_used` (validated by `order_payments.validate_provider_payment`) |
| Wallet top-up | `metadata.expected_amount_kobo` (set in `routes/wallet.py`) |
| Event ticket | `event_tickets.card_amount_used`; also written to `metadata.expected_amount_kobo` at initialize |
| Marketplace | `metadata.expected_amount_kobo`, added by `routes/marketplace.py` at initialize |
| HP bundle | `hp_amount × HP_BUNDLE_PRICE_PER_HP`; also written to `metadata.expected_amount_kobo` |

New card flows must record the server-side expected amount in the payment metadata when
there is no local row to read it from.

## What the webhook does afterwards

* **Marketplace** completes through `complete_marketplace_card_purchase`, so a purchase
  that cannot be fulfilled after the charge (sold out, price changed, HP/wallet shortfall)
  is refunded to the buyer's wallet instead of being dropped by a failed webhook. The
  refund uses the expected amount, so a gateway fee is never refunded as spendable balance.
* **Event tickets** are confirmed through `_confirm_event_ticket_charge`. A ticket
  cancelled/expired between checkout and the webhook still raises, because the money has to
  be refunded or the ticket re-issued — the error says so explicitly.
* **Every failure** is written to `webhook_events` with `status = 'failed'`, the error
  message, **and the campus id resolved from the payload**, so it appears in the
  campus-scoped admin log. Successful deliveries clear `error`.
* **Wallet top-ups** with no `user_id` now fail loudly instead of being marked processed
  without crediting anyone.

## Recovery paths (nothing is stranded)

1. **Automatic:** Paystack retries a non-2xx delivery; the claim logic re-opens a `failed`
   row, so a delivery failed by an old bug now succeeds on retry.
2. **On the customer's return:** `POST /events/<event_id>/tickets/verify` verifies the
   `reference` from the checkout redirect directly with Paystack and confirms the ticket
   (idempotent). `EventDetail` calls it before polling `my-tickets`, for signed-in users and
   for guests (using the email they registered with). `my-tickets` now returns
   `payment_status`, and the UI no longer treats an unpaid reservation as a confirmed ticket.
3. **Manual:** `POST /admin/webhook-events/<id>/retry` replays a failed delivery from the
   stored payload. Idempotent — an already-confirmed order/ticket/purchase is returned
   untouched. Super-admins may retry any row; a campus admin only their own campus's rows —
   including legacy failures stored with no campus, when the stored payload resolves to
   that campus (that is exactly how a stranded registration from before this fix is
   recovered without SQL).

## Admin webhook log

`GET /admin/webhook-events` stores `processed` / `failed` / `processing`. The UI's status
filter accepts `success`/`delivered`/`ok` (→ `processed`), `error` (→ `failed`) and
`pending`/`retrying`/`queued` (→ `processing`). A campus-scoped admin also sees failed
deliveries that have no campus; those rows have their raw `payload` redacted and
`payload_redacted: true`, because a global payload may belong to another campus.
