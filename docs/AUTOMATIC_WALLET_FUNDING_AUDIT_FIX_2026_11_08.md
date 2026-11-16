# Automatic wallet funding audit and fix — 8 November 2026

## Root cause of the checkout handoff failure

The Create recurring control was connected to `POST /api/wallet/auto-funding`,
and that route reached Paystack's `/transaction/initialize` endpoint with the
existing server-side Paystack configuration. Kobo conversion, the customer's
profile email, a durable `HG-AUTO-...` reference, card-only initialization, and
the Holy Grills callback were present.

The frontend then did this:

1. receive a valid initialization response;
2. `await` a second, unnecessary `GET /wallet/auto-funding`;
3. redirect only if that read also succeeded.

A failure in step 2 entered the setup-error handler and step 3 never ran. Thus
Paystack could initialize successfully while checkout never opened. The redirect
now uses the initialization response directly. The POST response exposes the
standard top-level `authorization_url` and `reference` fields, and retains
`plan.checkout_url` for compatibility and resumable first payments.

The backend also called `raise_for_status()` before reading Paystack's JSON error
body, then replaced all initialization exceptions with one generic message.
That suppressed the actual provider diagnostic. Initialization/verification
errors now retain a bounded, control-cleaned provider message. Recurring-charge
errors never echo provider detail, so a reusable authorization cannot leak into
a response or log.

No production code in this checkout emitted the literal **“clinic not found”**.
Its external/deployed origin cannot be proven from this repository alone. If it
is Paystack's JSON message, the new path returns that message (covered by a
regression test) instead of hiding it; unexpected route/database exceptions now
have server-side stack traces without request payloads or reusable credentials.

## Targeted fixes

- Redirect immediately from the successful initialization POST; a plan-list
  refresh can no longer block checkout.
- Added a synchronous operation lock in addition to the disabled/loading button,
  preventing rapid duplicate submissions. Existing request IDs remain the
  idempotency boundary for retries.
- Preserve meaningful initialization, verification, and stop errors. A wallet
  refresh failure after confirmed payment is no longer misreported as an
  unconfirmed payment.
- Validate Paystack's checkout URL before saving/using it.
- Accept both `reference` and `trxref` on return. After server verification and
  wallet refresh, clear the one-time callback parameters while retaining the
  expanded plan.
- Record failed/abandoned/reversed first payments during return verification;
  they do not activate an arrangement or credit a wallet.
- Recover a verified reusable first payment from the specific
  `setup_unavailable` state left by a lost initialization response. Stopped plans
  and previously failed payments are not reactivated.
- Added `20261108113000_wallet_funding_checkout_history.sql`. It replaces only
  the existing funding RPC: no table, ledger, or permission structure changes.
  It removes the silent five-plan list cutoff, returns up to ten safe attempt
  receipts per plan for expanded history, and includes the setup recovery above.

## Recurring-payment architecture audit

The existing implementation already uses Paystack reusable card authorization,
not Paystack native subscriptions:

- first successful card transaction is verified server-side;
- only a reusable card authorization with an authorization code is stored in the
  private `hg_internal` plan record;
- subsequent debits run in the existing 15-minute Celery worker using
  `/transaction/charge_authorization`;
- the SQL dispatch lease and immutable per-cycle reference prevent duplicate
  charge authority; an uncertain POST is never retried as a new charge;
- provider verification or a signature-checked `charge.success` webhook is
  required before the existing atomic wallet ledger credit;
- attempt state plus the wallet provider reference make callback/webhook replays
  credit and count only once;
- amounts are validated as exact kobo, the original profile email is retained,
  the first payment counts toward the limit, and count/end-date completion stops
  future dispatch and clears stored authorization;
- stop updates the same row and clears future charge authority. A late confirmed
  payment can still credit its owner without reactivating the stopped plan;
- failed, non-reusable, expired, changed-account, and uncertain authorization
  states pause future debits rather than inventing a success.

No working wallet or scheduler architecture was replaced.

## Collapsible interface and UX

- Current arrangements are compact rows showing amount, cadence, status,
  contribution progress, and total wallet funding.
- Only one arrangement expands at a time. Expanded details include safe attempt
  history, next scheduled contribution, card label, in-flight state, and actions.
- Stopped/completed arrangements remain in **Previous arrangements**, including
  accounts with twenty or more records.
- Create/verify/stop responses update records by ID; stopping does not append a
  duplicate card.
- The setup button shows a spinner and cannot be repeatedly submitted. Success,
  pending, failed/cancelled, and refresh-failure states have distinct messages.

## Verification performed

- Backend full suite: **1,355 passed** with disposable test-only environment
  values and all provider/database calls mocked.
- Focused automatic-funding suite: **23 passed**, including the standard checkout
  response, upstream diagnostic propagation, credential-safe charge errors,
  failed returns, single-attempt money POSTs, and existing owner/idempotency
  checks.
- Frontend ESLint and TypeScript: passed.
- Complete client/SSR build, frontend regression scripts, and prerender: passed.
- New migration and SQL acceptance script: PostgreSQL parser validation passed.
- Browser harness updated for mobile/desktop, double submit, post-create read
  failure, `trxref` return, one expanded row, and 21 retained arrangements. A
  Chromium binary was obtained, but this sandbox lacks its system NSS libraries,
  so the Playwright scenario could not launch and is **not reported as executed**.
- The SQL acceptance script was not run against production or a disposable live
  PostgreSQL instance because neither is configured in this sandbox.

## Required deployment/configuration and remaining live test

1. Apply the original automatic-funding migrations if not already applied, then
   apply `20261108113000_wallet_funding_checkout_history.sql` before deploying
   the UI history changes.
2. Deploy the backend **and Celery worker/beat** from the same revision. Both API
   and worker need the intended Paystack `PAYSTACK_SECRET_KEY`; use an `sk_test_...`
   value for acceptance testing. `FRONTEND_URL` must be
   `https://holygrills.online`, and Paystack webhooks must use the corresponding
   account secret and existing webhook URL.
3. In Paystack test mode, run the ten requested acceptance steps with a real
   test-card authorization: create, checkout, authorize, return, verify/save,
   advance a test arrangement's due time, run the worker, verify wallet credit,
   stop/limit/failure/replay cases. No Paystack or Supabase credential exists in
   this sandbox, so no real test-mode charge or live database write was claimed.
4. Run `scripts/test-auto-funding-browser.py` in an environment with Chromium's
   NSS runtime libraries (`libnspr4`, `libnss3`, `libnssutil3`) installed.
