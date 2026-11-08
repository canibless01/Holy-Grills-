# Automatic wallet funding

Implemented for the Holy Grills wallet. User-authorized fixed contributions are
spendable as soon as Paystack confirms payment. This is wallet funding, with no
interest, investment promise, withdrawal or lock period.

## Customer flow

- Dashboard now has four equal quick-action cards in a two-column grid on mobile
  and desktop: Events, Marketplace, Leaderboard and Automatic funding.
- Wallet includes a lazy-loaded setup/management panel and the funding dialog
  links to it. Closed panels and the Dashboard make no automatic-funding read.
- Choose an amount, every N days (1–365, including every two days), then a total
  contribution count (including the first payment), an inclusive Nigerian end
  date, or continue until stopped. Changing terms clears the consent checkbox.
- The first contribution is paid now through card-only Paystack checkout. This
  credits the wallet and establishes a reusable authorization when supported.
- Holy Grills absorbs fees: choosing ₦200 charges ₦200 and credits ₦200. Fees
  reduce merchant settlement, with no extra fee debit to the customer.
- Non-reusable cards still fund the wallet, but do not enable future debits.
- Stop controls are available for drafts, active plans and plans needing
  attention. A payment already processing may still finish and is credited.
  An open initial checkout link should be closed when its plan is stopped.
- Changing an amount or schedule requires stopping the old plan and consenting
  to a new one. One open plan per account prevents accidental parallel plans.

The minimum follows the existing `wallet_min_card_topup` system setting (Render/
Railway `WALLET_MIN_CARD_TOPUP` fallback), with a ₦100 recurring-funding floor.
The technical per-contribution cap is ₦1,000,000; counts are 1–3,650. These are
validation bounds, not new top-up bonuses. Existing qualifying top-up HP and
check-in reclamation rules still apply; small contributions do not bypass their
minimums.

## Money and scheduling guarantees

Paystack native plans cannot express every two days, so one custom scheduler
supports all selected day intervals through reusable card authorizations.
Original authorization email and reusable card context are retained privately.
Raw card numbers/CVV never enter the application. Browser responses and wallet
ledger metadata exclude reusable authorization codes.

Each plan and contribution has a durable, immutable reference. PostgreSQL locks
serialize setup intents, dispatch, cancellation and confirmation. Only one
worker can receive dispatch authority for a contribution. There is no automatic
retry of a charge POST. Timeouts, crashes and ambiguous provider errors trigger
GET verification of the same reference, blocking further charges until resolved.
A crash before sending can therefore require attention rather than risk a
duplicate debit. Failed payments pause the plan; there is no automatic catch-up
or accumulated debit. Long unresolved attempts reduce verification to six-hour
checks after the first day and surface an attention state.

Confirmed cash credits use the existing atomic wallet ledger in the same SQL
transaction as the contribution receipt and schedule update. Callback/webhook
replays cannot duplicate cash or contribution counts. A late success credits its
owner even after stopping, expiration or a prior failure, without reactivating
the plan. Paid money remains creditable if the account campus changes while the
payment is in flight; future debits require the original active campus binding.
Reward effects use the committed ledger campus and stable wallet receipt.

No extra Railway service or per-user cron is required. The existing Celery
worker and single beat scheduler run one indexed 15-minute scan, capped at 20
payment/effect items and a 45-second processing budget. Network operations are
bounded; an operation already running can extend that budget. Paused-plan
notices use a separate small indexed scan within that same task, durable leases,
stable notification identities and the existing notification dispatch recovery.
Missed windows never cause a burst of historical charges. The next contribution
is scheduled one chosen interval after the processed contribution; processing
is approximate to the shared scan cadence.

Optional Railway API **and worker** setting:
`WALLET_AUTO_FUNDING_ENABLED=false` stops new setups/debits. It defaults to true
and needs no new credential. Verification and credits for already-paid money
continue while disabled. Existing Paystack credentials, webhook and
`FRONTEND_URL` are reused. The API and worker both need the existing
`PAYSTACK_SECRET_KEY` for the intended payment mode. A worker without that key
does not claim new debit authority. Changing fees or terms requires a new consent version.

Both new tables are in `hg_internal`, with RLS and service-only access. Public
RPC entry points use security-invoker semantics and deny anon/authenticated
execution. Routes derive ownership from the authenticated session and are rate
limited. Only provider verification or a signature-checked webhook confirms cash.

## Verification

- Full backend suite: 1,311 passing tests; TypeScript and complete
  client/SSR/prerender build also pass.
- `tests/test_auto_funding.py`: exact cents, consent, owner checks, fixed fees,
  day intervals, trusted callback, card-only setup, setup replay, timeout without
  retries, verification-only recovery, isolated responses, emergency pause,
  ledger-campus effects and durable attention notices.
- `tests/sql/automatic_wallet_funding.sql`: actual production Postgres, all
  identities and money rolled back; zero retained audit users/plans. Covers
  unknown/underpaid/foreign references, duplicate intents, cash conservation,
  dispatch/stop, late successes, automatic count/date stop, non-reusable cards,
  failed payments, inactive members, service-only permissions and notice replay.
- `tools/verify_auto_funding_concurrency.py`: disposable local PostgreSQL,
  24 simultaneous setup intents, 36 first-payment confirmations, 24 dispatch
  claims and 36 racing stop/callback operations. Exactly two credits (₦400),
  one dispatch authority, and a stopped final plan. No provider POSTs.
- `scripts/test-auto-funding-browser.py`: native browser at 393px and 1280px;
  four equal cards, deferred reads, amount precision, frequency/count controls,
  explicit consent, safe checkout redirect, isolated return verification,
  two-step stop and in-flight notice, no horizontal overflow.
- No real card charge, refund, customer enrollment or blast used for testing.
  Actual card/bank acceptance and recurring authorization availability require
  the account holder's first live setup payment; provider-side card restrictions
  cannot be established by mocks or database tests.

The broader student-loading browser regression passes Dashboard, Wallet and
ordinary funding-return cases. Its fresh prerendered Home catalogue/ranking
cases expose React hydration error 421 under immediate synthetic responses.
An isolated build from the unchanged pre-feature commit reproduces the same
error, so this remains a separate existing storefront hydration audit item;
this release does not certify that all site performance work is complete.

## Wallet transfers: reviewed, not implemented

The existing HP transfer route validates sender, recipient, campus, minimum
activity and balance before its atomic HP RPC. Its interface can inform the
wallet experience, but cash needs its own exact-cents paired ledger operation
and an immutable transfer-intent receipt; copying the HP path alone is not
sufficient.

Proposed loop: find an eligible recipient using limited public identity fields;
show the verified recipient and exact amount; authenticate/confirm the sender;
commit both wallet ledger entries atomically with locks in stable user-ID order;
return a durable receipt to both users; recover notification dispatch separately.
Retries and lost HTTP responses reuse the same intent and never send again.
Transfers would conserve the combined wallet balances, charge no Paystack fee
for an internal ledger move, and create no top-up HP or streak-reclaim event.
Recipient eligibility/campus rules, limits, compromised-account controls,
reversal/support rules and treatment of subsequently disputed card top-ups need
to be decided before enabling transferable cash balances.
