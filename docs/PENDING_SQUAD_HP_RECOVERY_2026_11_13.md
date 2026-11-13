# Reserved squad HP recovery — 13 November 2026

Signup and the existing daily sweep now use the same backend-only atomic claim. The order lock precedes the recipient profile lock, matching delivery reward processing. A claim validates the actual active profile, email, campus, paid delivered squad order and completed distribution. It commits the HP award, WAT monthly tracker, pending-row marker and deterministic inbox/push receipt together. A lost response or simultaneous signup/sweep cannot grant or notify twice. Existing notification recovery handles committed push receipts; the HTTP path only wakes that saved work. No new scheduler, service, environment variable or session-hydration query was added.

Both historical reference keys (`squad_split`, `squad_split_claimed`) are checked. An existing exact active same-campus grant is adopted without another award or monthly increment. Conflicting amounts, multiple prior grants and ambiguous null-campus records remain pending for review; historical monthly totals are not guessed or rewritten. Invitation binding only fills unowned same-campus roster/member identities and checks the parent squad/order campus. Existing ownership is preserved. Tier refresh retains the prior best-effort behavior after commit; this batch does not certify all tier/milestone workflows.

Migration: `20261112193545_atomic_pending_squad_claims.sql`, applied before the corresponding runtime rollout. It adds functions only; no existing account, order, price or balance was changed by the migration.

Verification:

- Full backend suite: **1,658 passed**.
- Production `BEGIN/ROLLBACK` matrix: transaction interruption, replay, exact alternative-key adoption, conflicting legacy grant, inactive/cross-campus/unpaid denial, scoped invitation binding, preference suppression and backend-only execution grants. All fixtures rolled back; matching production fixture accounts: **0**.
- Disposable local database: **24 simultaneous signup/sweep requests**, including duplicate pending rows for the same order, resulted in one HP grant, one monthly increment and one inbox/push pair. Local fixtures removed. This concurrency harness supplements the production schema/RLS rollback test; it is not a production payment/provider send.
- Security advisors retained their preceding baseline; the new functions are invoker functions with fixed search paths, executable only by the backend service role.

Previous stock/report/handover/settings batch `6b814eb` has successful API, worker, single beat and Vercel deployment statuses. Broader remaining coverage is tracked separately; these results do not claim the entire historical audit is complete.
