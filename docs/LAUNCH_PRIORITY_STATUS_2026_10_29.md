# Launch priorities — current status, 29 October 2026

This is a current decision list, not a list of unbuilt features. Earlier audit logs record history; passing evidence here and linked domain reports supersedes older open entries. **The whole admin page-by-page/action-by-action audit is not complete.** Tested order/refund/batch/reward/ambassador/financial/campus boundaries do not certify every sidebar page. No defensible ecosystem-wide percentage exists without a fully executed action matrix.

## Closed in the latest batches

- Real Paystack TEST full-card, split, guest, unpaid-resume, webhook replay and corrected wallet-funding flows: PAY-01–07 in the [provider results](FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md).
- Admission at capacity two, paid overflow to tomorrow, capacity expansion move-up, one debit and complete moved-order timing metadata; explicit partial/full/delivered-refund review; generic physical-reward handover and rider settlement recording.
- Atomic delivery HP, pending unlock, welcome and missing squad-recipient recovery; ordering-streak HP now also recovers atomically against the original delivery week and saved terms. [Financial recovery](DELIVERY_REWARD_FINANCIAL_RECOVERY_2026_10_28.md), [streak recovery](ORDER_STREAK_RECOVERY_2026_10_29.md).
- Multi-gift campaigns and targeted promo quota/allocation/full-refund restoration cases. These are implemented, not still waiting to be built.
- Actual Cloudinary CMS upload/persistence/replacement and sample carousel rendering; tier-image containment; actual map/search/save with gate fallback. Upload concern is closed; final presentation is a separate check.
- Latest other-chat fixes are merged: public campus leaderboard peers, personal dashboard rank, deferred tier/reward loading, scarcity-label null handling and actual execution of scheduled monthly side inserts. The monthly worker has not been deployed or proven running.
- FUTA's supplied 51 departments/ten schools are live; mobile/desktop signup uses school → department selection. [Catalogue evidence](FUTA_SIGNUP_REFERENCE_DATA_2026_10_29.md).

## Must resolve before enabling the affected launch path

| Priority | Remaining work | Practical completion condition |
| --- | --- | --- |
| Core | Launch-supported promo/HP/squad/order-lock/campaign/earned-reward combinations and their cancellation/refund variants | Execute the allowed combinations with quote/charge/benefit/HP conservation; explicitly reject unsupported combinations. Wider timeout/late-payment/post-cancellation/refund variants remain beyond the seven provider cases |
| Core | Remaining menu-linked/special physical rewards and delivery exceptions | Test selected launch reward types through kitchen/rider, failed/unclaimed delivery and refund/restoration. Generic reward delivery already passes |
| Core | Remaining delivery-hook outage recovery | Tier/milestone/login-reclamation/legacy gift hooks still need durable recovery. Order-streak and core financial recovery are now closed; do not repeat them as unimplemented |
| Messaging | Durable application email counters, saved dispatch/retry and recovery | Finish the reviewed draft plus application integration, real SQL concurrency/lease tests and worker re-drive. Current quota-rejection fallback and real Resend delivery pass, but are not durable cross-worker quota accounting |
| Messaging | OneSignal registration and actual device delivery/click | Resolve dashboard origin configuration for the actual `www.holygrills.online` redirect and email-sending permission where needed; execute bounded real recipient subscription/receipt/click checks. No broadcast is needed to verify this |
| Operations | A running worker/timer for features promised at launch | Choose and verify actual execution/recovery, or keep the dependent scheduled features disabled and define explicit manual operations. No external cron/hosting migration has been deployed because the user deferred it |
| Access | Remaining action matrix for enabled admin/role workflows | Student/guest/own-campus admin/other-campus admin/super-admin/kitchen/rider/community-manager checks, negative/repeated/concurrent requests and persisted outcomes for the remaining actions. Whole-page approval is still open |
| Release | Production content/configuration smoke and account/data reset | Confirm reference data and stock/capacity/fees, rehearse dependency-safe cleanup preserving intentional content, bootstrap the real super admin, verify clean signup and one bounded release smoke. [Prepared reset plan](PRE_LAUNCH_CLEANUP_PLAN_2026_10_29.md); no deletion yet |

Actual Chrome native installation remains a release requirement **if the launch promises an installed PWA**. Deployed manifest/icons/HTTPS/service-worker technical checks pass, but the user's missing native menu entry remains unresolved on devices. A working website does not close this PWA-specific issue.

## Can follow after launch if their entry points stay disabled

Events/tickets/check-in, marketplace/subscriptions/codes, broader catering flows, advanced inventory/report/export/history matrices, and every nonlaunch admin setting still require their domain audit. They are not certified by the order audit or a table inventory. Broad visual redesign, spin-wheel refinement and remaining cosmetic storefront variants can follow; content visibility, returning-user loading and functional checkout presentation must still work for launch. Financial/stock correctness used by enabled checkout remains core even if advanced inventory UI is deferred.

The full original A/B domain scope is [here](REMAINING_ECOSYSTEM_AUDIT_SPLIT.md); [admin inventory and tested coverage](ADMIN_AUDIT_COVERAGE_STATUS.md) distinguishes mapping from verification. No new automatic cron, Auth policy, cleanup or provider origin mutation is implied by this document.
