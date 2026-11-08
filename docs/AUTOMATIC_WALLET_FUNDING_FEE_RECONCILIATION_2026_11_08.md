# Automatic wallet funding: Paystack fee reconciliation

## Scope

Automatic wallet funding now uses the same fee-aware amount reconciliation pattern as ordinary Paystack wallet/order payments. No global Paystack setting was changed, and ordinary food-order and ordinary wallet-funding code was not modified.

There are **no new fee columns or tables**. The existing wallet ledger diagnostic metadata remains unchanged; the feature does not add dedicated processing-fee storage.

## Payment behavior

- Initial checkout requests the selected wallet contribution in kobo and restricts checkout to `channels: ["card"]`.
- Subsequent Charge Authorization calls request that same contribution. Both request types include server-written `expected_amount_kobo` metadata for consistency with ordinary wallet funding.
- Paystack remains responsible for calculating and displaying its applicable processing fee. The application does not add a second local markup or hardcode a fixed fee.
- Initial return verification, signed webhooks, and later authorization-debit verification all use the same atomic confirmation function.
- New arrangements use consent version `wallet-auto-funding-v2`; the UI states that the customer pays the contribution plus Paystack's processing fee and that Paystack shows the initial total before authorization.

For a successful verified NGN transaction, the locked plan's `amount_kobo` is the expected contribution. Confirmation accepts only one of the established reconciliation cases:

1. `paid == expected`;
2. `paid - fees == expected` when Paystack supplies fees; or
3. when fees are absent, `expected <= paid <= expected + max(15000 kobo, 2% of expected)`.

If `requested_amount` is present, it must equal the expected contribution. Any other amount, currency, reference, owner, or requested amount is rejected. A successful confirmation credits **only the plan contribution**, never the fee-inclusive gross. Existing idempotency, reusable-card checks, failure handling, stop behavior, and private authorization storage remain in place.

## Required deployment order

1. Ensure the original automatic-funding schema migration has been applied once:
   `holy-grills-backend/migrations/20261108100151_wallet_automatic_funding.sql`.
2. Ensure the checkout/history function migration has been applied once where absent:
   `holy-grills-backend/migrations/20261108113000_wallet_funding_checkout_history.sql`.
3. Apply the new function-only migration before deploying the backend:
   `holy-grills-backend/migrations/20261108231500_wallet_auto_funding_fee_reconciliation.sql`.
4. Deploy the backend and frontend together. New frontend consent uses v2, which the new function accepts.

The new migration replaces only `public.hg_wallet_auto_funding`; it does not alter tables, credits, global provider settings, or ordinary payment functions.

## Validation completed locally

- Focused payment/backend selection: **55 passed**.
- Complete backend suite: **1,358 passed**.
- Frontend TypeScript typecheck: passed.
- Frontend ESLint: passed.
- Complete frontend production build and its route/prerender checks: passed.
- PostgreSQL parser accepted all three automatic-funding migrations, including the new three-statement function-only migration.
- `git diff --check` and Python compilation checks: passed.

The SQL transactional test fixture and disposable-database concurrency utility now cover fee-inclusive initial and subsequent confirmations, requested-amount mismatch, the bounded unknown-fee fallback, over-buffer rejection, exact wallet credit, replay protection, and stopping. They were updated but **not executed against PostgreSQL** because no disposable database/Docker service is available in this environment.

## Provider acceptance still required

No Paystack test or live transaction was initiated by this implementation. The repository's synthetic browser script was not run. The user will perform provider acceptance on their own account; Paystack test mode is recommended before live charges.

Acceptance should confirm, without exposing reusable authorization codes:

1. A selected ₦200 contribution opens card-only checkout and Paystack displays the total including its fee before payment.
2. Verified success records/credits exactly ₦200, not the gross.
3. A subsequent Charge Authorization debit receives the same reconciliation and exact ₦200 credit.
4. Wrong/requested amounts and over-buffer unknown-fee payloads do not credit.
5. Failed payments do not credit, webhook/callback replays credit once, and stopping prevents new debits while allowing an already-processing verified payment to finish.
