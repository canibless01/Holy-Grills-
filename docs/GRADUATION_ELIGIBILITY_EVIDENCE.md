# Graduation eligibility and claim evidence — 21 October 2026

Graduation claims require the account's configured graduating level, at least three paid delivered orders from its campus, and an active Graduation / Convocation calendar entry covering today in WAT. Semester/exam entries do not open claims. The admin calendar supports the new period type with inclusive start/end dates; no new table was added. Campus entries and global entries are scoped to the account's campus. The existing Rewards layout is preserved: a small claim action appears in My Rewards only after server eligibility succeeds, with no level advertisement or large graduation banner.

The private claim function commits the HP ledger, monthly earning counter, tier update and claim marker together. A historical graduation earning receipt repairs an unset marker without another award, even after configuration, level or calendar changes. HTTP requests cannot supply a different user or award amount. Postcommit notification failures do not report a saved award as failed.

## Verification

- Eight focused HTTP/configuration/recovery tests passed.
- Nine real database transaction assertions passed with final ROLLBACK, including wrong level, insufficient paid orders, foreign campus/semester/expired periods, inclusive dates, historical replay and private caller guard. Deliberately overflowing the monthly counter after the earning operation rolled back the ledger, balance and marker together: [transaction results](GRADUATION_TRANSACTION_EVIDENCE.json).
- Native browser against actual frontend/backend/Supabase: ineligible account had no claim advertisement; configured eligible state showed the compact action; three competing claims awarded `[1000, 0, 0]`; a stale browser click safely replayed the award; reload hid the action: [browser results](GRADUATION_BROWSER_EVIDENCE.json).
- Native eligibility prerequisites used isolated, explicitly synthetic paid delivered order history. This is not evidence of card settlement or a full kitchen/rider delivery. No customer data or fixtures were deleted; cleanup remains paused.

## Database history and access

Applied once as `20261021091014_graduation_eligibility_atomic`; canonical migration is under `holy-grills-backend/migrations/` with that exact version. One eligibility signature and one claim signature exist. Anonymous and authenticated database roles cannot execute either function; service role can. Existing academic-calendar policies/grants remain unchanged. The original calendar CHECK was extended to include graduation.

Remaining: public provider notification delivery and the full calendar-to-operational scheduling matrix. A legacy claimed marker without any matching earning receipt requires explicit investigation; the new transaction prevents that state for future claims.
