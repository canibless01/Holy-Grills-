# Signup welcome free-side credit

This bounded change replaces new physical first-order gifts with a configurable signup free-side credit. It does not implement the requested general time-based, multi-benefit promotion engine.

## Behavior

- New eligible student accounts receive the configured credit count once. Campus configuration overrides global defaults; the rollout default is enabled, one credit, valid for 60 days.
- The existing `free_side_credits` ledger stores the grant under a deterministic per-account UUID with source `signup`. No table or column is added.
- The private atomic function serializes grants through the existing profile row. An existing receipt is returned without changing its balance or expiry, including when it has been consumed, expired, or the configuration has changed.
- A private global cutover timestamp checks the actual Auth account creation time, so pre-rollout accounts do not receive retroactive signup credits. Recovery can grant an eligible post-rollout account that has no receipt when the feature is enabled; pausing the configuration prevents new grants while paused.
- Registration attempts the grant only after required profile persistence. `/auth/me` retries safely for an active existing profile. A grant outage does not convert a saved registration or valid login into a failure.
- Admin onboarding edits the current header-selected campus; super admins can edit global defaults through All Campuses. It shows whether the displayed campus config is inherited. Invalid settings, write refusals and competing first saves do not report a false successful save.
- The migration disables future legacy physical first-order gift grants. Existing gift rows and zero-price receipt items are preserved, and their fulfillment controls remain available. Invalid legacy launch dates fail closed.

## SQL review and access

Canonical SQL: `holy-grills-backend/migrations/20261021092017_signup_welcome_credit_atomic.sql`. Parent reviewed and applied it successfully once to Test Two, recorded as server migration version `20261021092017` / name `signup_welcome_credit_atomic`. It seeds configuration using the existing partial unique indexes, retaining an existing rollout timestamp on retries. SHA-256: `ac4d1c1a227a2a52951612c65382c6ac14c8a5626cf0262a2f05f4786c210343`.

`hg_grant_signup_free_side_atomic(uuid)` is explicitly executable only by `service_role` (plus the database owner), never `PUBLIC`, `anon` or `authenticated`. It validates the target account, role, campus, account-creation cutoff and scoped configuration inside the transaction. Ordinary administrators edit settings through the existing RLS-protected settings table; the dedicated route restricts global writes to super admins and ignores a campus admin's attempt to target another campus.

## Local checks

- `tests.test_welcome_credit`: **12 passed**, covering strict config bounds/types, campus inheritance, role/scope guards, generic settings validation, save refusal/conflict behavior, fixed server identity, and registration/auth recovery failure boundaries.
- Frontend TypeScript validation and owned admin-file ESLint: passed.
- Source diff whitespace check: passed.

## Live verification

The parent ran `/workspace/work/ecosystem-audit/signup-welcome-20261021/verify.py` successfully against Test Two after applying the migration. Recorded results are in that directory's `live.log` and `results.json`:

- The actual `/auth/me` recovery path granted one campus-configured welcome credit.
- Four concurrent grants created one receipt: one grant and three idempotent replays.
- Replaying a simulated spent/expired receipt did not refill it or extend its expiry. This verifies replay protection, not food-order consumption.
- A disabled campus override prevented a grant while the global default remained enabled.
- Changing the admin configuration did not alter a previously granted balance or expiry.
- A pre-rollout Auth account received no retroactive credit.
- An ordinary authenticated user could not execute the private grant RPC directly.

The harness used the known audit campus and three newly journaled verified fixture accounts. It restored the original owned campus configuration, performed no deletion or database cleanup, and retained its fixtures for the explicitly paused cleanup. Its private journal blocks blind retries after interruption.

The controlled admin browser check is still pending. A real public signup/verification-email delivery and a native free-side selection → paid order → kitchen/rider fulfillment remain outside this bounded evidence. Auth fixture creation bypassed public email verification, so the successful live checks do not claim email-delivery proof.
