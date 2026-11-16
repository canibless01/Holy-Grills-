# Weekly check-in payout recovery — 5 November 2026

All attendance days/weeks use Africa/Lagos. This report supersedes the weekly-payout gap in the preceding check-in reclamation report.

## Fixed

Previously the service attempted pending HP, swallowed a failed grant as zero, and then advanced the week anyway. A committed grant followed by response loss could also repeat the separate monthly-counter write. Notification failure was mixed into the grant result. The customer-facing reward preview and backend payout additionally read different configuration stores.

The new service-only, security-invoker transaction locks the recipient and saved attendance, evaluates the completed week, writes pending HP and its monthly tracker, saves an immutable outcome receipt and advances the week together. A financial failure rolls the transaction back and leaves the week available for retry. A committed replay awards zero additional HP and returns the saved outcome; changes to settings do not rewrite that receipt.

- Five or more valid checked/reclaimed days complete the week: up to two missed days. Four valid days reset the cycle. Invalid/out-of-range day entries do not count.
- Missed whole weeks cannot pay an older good week. Messages identify the actual completed/missed week and exact missed-day count.
- Week 4 remains the plateau, but each calendar week has its own deterministic payout reference. Prior Week 4 grants do not block a later week's payout.
- The authoritative reward source is now the same `login_streak_rewards` JSON setting rendered by the app, preferring the recipient's campus then global. Missing week values fall back to the existing reward table. Invalid configured amounts fail closed. The current production amounts remain **25, 40, 60, 80 HP**.
- Existing boosts apply once, and receipts/messages show the amount actually credited after the cap. A capped valid week remains completed and explains the monthly limit.
- Existing monthly pending-cap accounting keeps its prior UTC month basis. Attendance weeks remain WAT. The existing pending-balance ceiling is unchanged; if it rejects a grant, week advancement does not discard the unpaid outcome. This failure remains retryable after pending HP is unlocked. No new ceiling or reward amount was introduced.
- Legacy ledger collisions link the existing business payout without another credit or speculative tracker increment. Historical unlocked/partial awards are not guessed or backfilled.

Both migrations are applied:

- `20261105031040_atomic_weekly_login_payout.sql`
- `20261105031428_use_configured_weekly_login_rewards.sql`

No new environment variable is required. The old `LOGIN_STREAK_WEEK1_HP` through `LOGIN_STREAK_WEEK4_HP` configuration names are legacy values and no longer override the transactional payout. Edit the JSON reward setting; the [settings map](SETTINGS_AND_ENVIRONMENT_MAP_2026_10_30.md) now says so.

## Notice recovery

The saved weekly outcome starts unacknowledged. If persisting its notification fails, a later login retries the notice even when today's attendance is already checked. Its deterministic per-user/week reference prevents duplicate stored notifications and distinguishes later weeks. A separate acknowledgement changes only the matching receipt, so an old callback cannot acknowledge a newer outcome. An opted-out channel is respected.

This covers recovery before a notification is persisted. External email/push still uses the existing dispatch path; a provider/process crash after persistence is **not** certified as durable delivery by this change. Stored notification, provider acceptance and customer receipt remain distinct.

## Verification

- **1,038 backend tests passed**, followed by the focused 12-test weekly recovery suite including the additional next-login notice-recovery case. Message-registry check passed.
- `tests/sql/weekly_login_payout_rollback.sql` passed before and after deployment of the functions. It exercises transaction interruption, committed-response replay, five/four check-ins, exact misses, edited/zero rewards, JSON precedence/table fallback/invalid configuration, monthly partial/full caps, pending-ceiling failure and retry, skipped weeks, Week 4 reference isolation, one boost, acknowledgement matching and service-only execution.
- Nine synthetic actors and all financial/settings/attendance changes were rolled back. Fixture count was zero afterward; production's 25/40/60/80 JSON values were checked unchanged.
- Security-advisor results were unchanged: five existing findings, no new finding.
- No historical live user's weekly rewards were replayed, no provider broadcast or charge was made, and no test account/order was retained. No scheduled job was removed or added.

Ordinary production weekly execution/first real customer payout and independent simultaneous database sessions are still operational observations to collect. The broader physical-device/payment/admin/legacy-gift and durable external dispatch exceptions remain in the [launch acceptance checklist](LAUNCH_ACCEPTANCE_2026_11_04.md).
