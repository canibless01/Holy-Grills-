# Stock, handover and settings loop closure — 12 November 2026

## Stock report and export

Admin → Store / Stock now has **Stock report & CSV**. Select WAT dates to inspect each ingredient's opening, purchases, usage, waste, signed corrections and period closing in its own usage unit. Current balance is compared separately with the complete ledger. Mixed ingredient units are never added into an invented total. Recorded purchase costs and purchases without costs are distinct. Archived ingredients remain available. A super admin can inspect the all-campus report; stock management still requires a selected campus. CSV uses the same returned snapshot and protects spreadsheet formula fields. Failed reads hide incomplete data and retain date/Retry controls. The report is read-only and never posts a correction or adjusts a balance.

Migration `20261112190643_stock_reporting_and_durable_alerts.sql` adds a backend-only scoped report and private low-stock episode state. A low-stock notice and its durable push receipt now commit in the stock transaction. Further usage while already low and adjustment replay do not spam new alerts. Replenishment re-arms the next episode. Authorized authenticated threshold edits also create the private receipt. Inventory notices are operational, not marketing; channel opt-outs remain respected.

The updated dispatcher verifies that stock is still low and its episode is still current, including a final database check before provider handoff. Replenished/archived/superseded alerts are skipped honestly. The existing recovery worker handles saved receipts if the API process exits; a bounded asynchronous wake gives queued notices an immediate attempt without holding the HTTP response. No new periodic task, service or environment variable is added.

## Physical handover recovery

Migration `20261112191316_atomic_prize_handover_notices.sql` makes leaderboard, Hall of Fame and physical-spin status changes commit with their audit/inbox/push receipts. Note edits and response-loss retries preserve the original fulfilment actor/time. Closed prizes cannot be reopened by direct browser writes. Automatic HP/delivery/multiplier spin awards are excluded from this physical-handover guard. Old prepared notices are skipped if the prize is subsequently fulfilled; earned state is not silently replayed from historical rows.

The production rollback test caught a dispatch diagnostic-column mismatch. Corrective migration `20261112191344_stock_prize_dispatch_result.sql` uses the existing `error_message` column. Both original history and correction are retained; final production matrices pass. No historical customer status or notification is backfilled.

## Campus flags and active-account permissions

Implicit feature checks now resolve the authenticated campus, the super-admin's selected campus, or the guest's validated campus header. Explicit worker scopes remain authoritative; jobs without a request retain global fallback. This closes legacy override bypasses in free-side, spin, HP-transfer, Hall of Fame and scheduling gates. Scheduling passes its actual admission campus explicitly, including calls outside HTTP. Paused-gate tests execute the real endpoints and stop before balances, rewards, transfers or calendar admission. No live feature switch changes.

Migration `20261112192103_active_staff_policy_helpers.sql` adds the persisted active-account check to the existing `hg_current_user_role` and `hg_is_admin` helpers. The active staff result and execution grants stay unchanged. The fresh settings matrix verifies global versus campus edits, private versus public settings, invalid welcome-HP values, student/community-manager denial and deactivated kitchen/admin/super-admin identities reusing their old token claims. Older kitchen-setting/cron/Hall-of-Fame/partnership policies using these helpers now lose elevated access after deactivation; newer campus-admin policies already had that check.

The 17 live flag names were traced to their Python/SQL/frontend consumers: cart recovery, birthday HP, events, exclusive spin, flash redemption, free sides, Hall of Fame, expiry warnings, multipliers, HP transfer, leaderboard prizes, marketplace, referral milestones, scheduling, squads, subscription codes and wallet transfer. Existing dedicated monthly-task consumers already merge explicit campus overrides. Disabled features remain disabled. This consumer tracing and targeted gate proof do not claim new event/marketplace implementations.

## Verification

- **1,650 full backend tests passed**, including native endpoint gate/validation and notification-recovery contracts.
- Frontend typecheck and complete client/SSR/prerender build passed.
- Four built-app cases passed: mobile report/CSV, failed-read Retry, All Campuses and committed-response-loss physical-prize handover retry.
- The existing native stock suite passed create/purchase loss recovery, unit/cost/actor ledger fields, signed corrections, usage/waste, ledger paging/Retry, stale-campus isolation, metadata conflicts and archive/restore/replay.
- Three fresh production BEGIN/ROLLBACK matrices passed: populated stock report/alert/replenishment/send-boundary checks; all three physical-prize handovers/audit/receipts/terminal guards; and settings/staff RLS boundaries. Stock and prize matrices were repeated after the helper hardening. No provider send, genuine order or retained fixture was used. Matching fixture accounts remaining: **0**.
- Security advisors remain at the pre-existing 2/1/13/22/1 baseline; none names the new report, episode, handover or validator functions.

These close the named inventory, handover and settings-access loops. The remaining legacy signup-time squad-share claim path is being examined separately; broader historical schema cleanup and unrelated newsletter/CMS/presentation variants are not certified by these cases.
