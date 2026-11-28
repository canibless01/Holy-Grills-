**Reset update — 30 October:** the authorized database cleanup is now completed and independently verified. See [completed reset and preserved configuration](PRE_LAUNCH_RESET_COMPLETED_2026_10_30.md). Earlier “not executed” notes below are historical. Real owner/admin setup and final release smoke remain.

# Remaining work after the kitchen action run — 30 October 2026

This is work still requiring verification and fixes where tests expose defects. Most underlying features already exist; this is not a list of features that must all be built. Historical A/B ownership is not evidence that a second chat finished its share. The whole admin page-by-page audit remains incomplete.

## Current run completed

Kitchen explicit-campus workspace/settings and global feature-flag scope fixes were pushed in `7ed342c` and `8d0938a`. The [current kitchen action evidence](KITCHEN_ACTIONS_EVIDENCE_2026_10_30.md) adds prep-window race/retry protection, batch action guarding/refresh and correct persisted campus stock controls. Latest backend suite: **778 passed**.

## Remaining for enabled launch paths

1. **Promotion/reward combinations and payment interruptions.** Finish the supported promo + HP + squad + order-lock + campaign + earned-reward combinations, cancellations, partial/full refunds and benefit/HP/stock restoration. Extend interruption/late-payment/post-cancellation recovery beyond the seven successful real gateway cases. Multi-gift checkout, targeted refund conservation and real card/split/guest/funding cases are already implemented and verified for their recorded cases.
2. **Physical rewards and delivery exceptions.** Exercise remaining menu-linked/special/legacy reward types through checkout, kitchen, rider handover, failed or unclaimed delivery and refund/retry. Generic physical reward handover, basic batching, assignment/reassignment/splitting and capacity rollover/move-up have passing evidence; broader variants remain.
3. **Remaining delivery reward recovery.** Tier/milestone/login-reclamation/legacy gift hooks still need outage/replay recovery. Core delivered HP, pending unlock, welcome/squad financial credit and ordering-streak recovery are already closed for documented cases.
4. **Durable application email dispatch.** Implement persistent quota counters, saved dispatch/retry/lease/recovery using the reviewed existing-table design, then test concurrent workers and re-drive. Real Resend and explicit quota-rejection fallback already pass. Supabase Auth SMTP is a separate channel. The durable dispatch draft is not applied.
5. **Real push and scheduled execution.** The deployed OneSignal CSP correction and real SDK initialization now pass. Finish actual recipient subscription, identity/backend persistence, receipt and notification click destination. Worker/timer execution and recovery are still not deployed/proven. The user deferred external cron/hosting migration; either run and verify the necessary jobs before promising their features or keep those features disabled with explicit manual operations.
6. **Returning-user startup and release surfaces.** Retest first load, restored login/campus, return from background, menu/reviews/hero visibility and initial API failures. Settled carousel samples and Cloudinary uploads pass. The other chat fixed a shared PWA/OneSignal service-worker reload defect in `c99ac60`, with an integrated controlled browser regression; verify its live returning-user outcome and the earlier empty-hero/public-config timeout. Finish residual CMS scope/sort/concurrent-write and presentation variants, plus newsletter delivery if enabled.
7. **Remaining enabled admin and role actions.** Complete the matrix below, including field-level availability/pricing permissions, retries, cross-campus negatives and customer-facing persisted results. Inventory/opening a page is not whole-page approval.
8. **Release preparation.** Confirm actual capacities, admission stock, fees, contacts/social links, active promotions and school reference data. FUTA now has 52 department options/11 school labels including Postgraduate; no 600 level was added. West/South gate coordinates still need physical confirmation, and the academic period end date needs owner confirmation. Rehearse and execute the dependency-safe test-data reset only at the release step, preserving intentional menu/storefront/reward/media/configuration. Bootstrap the real super-admin and community-manager system actor, verify clean signup/email reuse, then one bounded release smoke. Cleanup has NOT run.

**PWA:** the missing Chrome native install entry on the user's desktop/mobile still needs device-level closure if installation is promised at launch. Manifest/icons/HTTPS/service-worker technical checks pass. Browser version, installation state and actual Chrome installability behavior must be checked on the affected devices; a source check alone cannot certify the menu entry.

## Admin page/action matrix still open or partial

| Group | Remaining scope |
| --- | --- |
| Menu Items; Add-ons & Variations | Complete field/input/delete/restore/sort/availability and pricing-role cases; public item/cart result and contention beyond targeted successful loops |
| Orders; Delivery; kitchen/rider panels | Remaining filters and operational actions, unusual batch/delivery transitions, failure recovery and payout/report consistency |
| Wallet; financial controls/reports | Remaining administrative actions, reporting/filter/export checks and wider reconciliation exceptions |
| Promo Codes; Order Locks; Abandoned Carts | Complete supported stacking/restoration, scheduling/reminders, targeting and customer outcomes |
| Rewards; Free Credits; Exclusive Spin; Challenges; HP & Multipliers | Remaining earned reward types, milestone/tier/retention loops, grants and fulfillment variants; preserve completed atomic financial/streak proof |
| Feature Flags | Global controls and override visibility pass; complete every enabled UI/API/task consumer and disabled-state matrix |
| Users; staff; profile/onboarding | Complete signup/login/reset/profile, permissions, role changes, activation/suspension and gifting/preference variants |
| Campus management | Remaining campus controls and consumers; Departments/Levels, Calendar, Gates/Hostels and Delivery area have their documented completed batches |
| Store/Stock | Enabled checkout stock correctness stays launch-critical; advanced inventory operations and complete interface/report matrix remain |
| Dashboard; Analytics; Economics; Leaderboard; Reviews | Controlled producer-to-report comparisons, all filters/pagination/exports, moderation actions and remaining role/privacy cases |
| Notifications; preferences; newsletter | Blast targeting/preview/counts/repeat prevention/scheduling, consent, real receipt/deep links and provider/worker recovery |
| Settings; System; Webhook diagnostics | Trace remaining fields to consumers, remove/repair dead controls, verify scope/access and diagnostic/replay actions |
| Storefront | Upload concern closed; residual edits/sort/scope/concurrency and first/return startup checks remain |
| Community manager / ambassadors | Existing creation/grant/caption/share/measurement proof is retained; remaining actions and exceptional permission/report cases still require the same complete matrix |

Completed page batches are recorded in [admin coverage](ADMIN_AUDIT_COVERAGE_STATUS.md). Existing successful order/financial/provider tests are retained; they are not all waiting to be repeated from scratch.

## Can follow after launch while disabled or not promised

- Events/ticketing/check-in and exceptional HP/scan/recovery/report cases.
- Marketplace, trading, subscriptions and codes.
- Broader catering request/quote/status/fulfillment cases.
- Advanced inventory, analytics/report/export/history and nonlaunch system controls.
- Broad visual redesign, spin-wheel polish and cosmetic storefront variants. Content visibility, clear checkout and functional paid-order fulfillment remain launch requirements.

Do not delete test accounts now, activate deferred scheduled features, change provider origins or deploy external cron as a side effect of this list.
