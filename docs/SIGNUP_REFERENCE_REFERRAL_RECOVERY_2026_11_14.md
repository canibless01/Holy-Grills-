# Signup reference loading and referral entry — 14 November 2026

Fixed newly copied referral and ambassador links to use `/register?ref=CODE`. Both continue using the account's existing referral code: signup submits it to the existing referral service, while ambassador click/visitor attribution uses the separate existing programme tables. No replacement code, duplicate HP award or parallel referral ledger was introduced. Existing guest `/?ref=CODE`, `/?referral=CODE` and `/r/CODE` links now reach signup with its referral input populated. A signed-in customer's root link remains a browsing entry. Tracking observes SPA link changes and suppresses the redirect's duplicate click.

Registration still uses one public database reference RPC. Successful public reference snapshots are reused for 30 seconds per campus/app worker (bounded 32-key cache, copied results). The browser reuses a campus-scoped session snapshot for 60 seconds, including page reload, and coalesces concurrent reads. It retries a transient network/429/5xx read once after 400ms, with a 20-second attempt deadline. Retired/invalid campuses are not retried; expired snapshots do not hide errors; the existing Retry and campus selector remain available. Account creation is never automatically retried. Server-side signup continues checking the actual active department, level and campus, regardless of cached options. This improves repeat loads and transient recovery; it cannot eliminate a device's network outage.

Verification:
- 102 focused backend tests pass: real signup query transport, scoped reference cache expiry/copy/error handling and ambassador programme/referral attribution contracts.
- Frontend reference test passes coalescing, one transient retry, campus isolation (including implicit stored campus), cached reload, TTL, force refresh and bounded errors.
- Native Chromium: old root referral reaches signup; first reference request fails with 503 and automatically recovers; faculty/department/level selection works; reload reuses the snapshot; referral code is submitted; issued session reaches Home. `/r/CODE` also prefills signup; the redirect records only one ambassador click per load. All HTTP controlled; no production account or email created.
- TypeScript, edited new components/helper ESLint and complete client/SSR/prerender build pass.

No schema migration, price edit, customer-data mutation or new scheduled task.
