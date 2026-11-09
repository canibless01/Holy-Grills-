# Same-campus wallet transfers

Wallet → **Send money** lets a student look up an active same-campus friend by referral code, review their name and amount, and confirm. The recipient can spend the funds immediately. Both parties get an owned receipt through transaction history and notification links. The lookup does not expose email, telephone, or another person's balance.

Transfers move existing wallet funds internally. There is no Paystack charge, transfer fee, top-up HP, or change to automatic funding. Delivery fees and checkout remain separate.

## Controls

- Feature Flags: `wallet_transfer`; campus overrides take precedence. Disabling new sends preserves owned receipts and completed-request recovery.
- System Settings, in naira: `wallet_transfer_min_amount` (initial global ₦1), `wallet_transfer_max_amount` (₦1,000,000), `wallet_transfer_daily_limit` (₦1,000,000 outgoing per Africa/Lagos calendar day). Campus settings override global values. These are editable in app; no new Render/Railway or Vercel environment variables are needed. Existing values are preserved by migration.
- Active sender and recipient must share a campus at confirmation. The server derives sender identity from the authenticated session and rechecks recipient code, campus, balance and limits inside the locked transaction.

## Money and interruption handling

One database transaction locks both wallets in consistent order, debits and credits equal amounts, records both existing wallet-ledger entries, and saves an immutable transfer reference. Existing wallet triggers keep profile mirrors synchronized. No provider calls occur inside this transaction. A failed second credit rolls back the first debit.

A client-generated UUID identifies one frozen set of transfer details. Repeating it returns the original receipt; changing those details rejects the request. Client storage is scoped to the signed-in account. A timeout preserves the reference and offers receipt lookup or retry of that same intent. A missing receipt alone does not authorize a replacement transfer. Only an authoritative validation rejection permits editing and a new confirmation.

Receipt delivery happens after commit through the existing Celery worker. A private receipt outbox recovers interrupted handoffs through the existing 15-minute recovery job, without another recurring scheduler. Stable notification IDs adopt existing rows after crashes; the existing notification outbox handles interrupted external delivery. Money is never resent by notification recovery.

## Verification

- Backend unit tests cover exact decimal validation, server ownership, private error handling, post-commit broker failure, and bounded receipt recovery.
- `tests/sql/wallet_transfers.sql` passes locally and in Supabase inside BEGIN/ROLLBACK: conserved balances, paired ledger entries, mirrors/no HP, same-campus and active-account checks, owned receipts, replay/conflict, limits, insufficient funds, partial-credit rollback, empty-wallet creation, disabled flags, and receipt recovery leases/privileges. No fixture accounts or transfer rows remain.
- `tools/verify_wallet_transfer_concurrency.py` runs only in a disposable local Docker database: 16 identical requests create one debit/credit pair; competing requests cannot overdraw or bypass daily allowance; opposing transfers complete without deadlock.
- Native browser tests cover mobile/desktop confirmation, decimal validity, success/history receipts, unknown POST result and same-reference retry, committed-response loss followed by reload recovery, authoritative rejection, and a disabled send gate with a private receipt lookup.

The checks do not make a real customer transfer or charge a card. Production deployment status and authenticated device usage are separate from the transactional fixture checks.

Release verification after integrating `f8dc24b`: **1,404 backend tests passed**; TypeScript and the full client/SSR/prerender build passed; all **six transfer browser scenarios** and all **six page-performance browser scenarios** passed. Supabase service-role read/write checks passed with all fixtures rolled back; security-advisor category counts were unchanged. Wallet displays preserve up to two decimal places so the confirmed amount, receipt, ledger and visible balance agree.
