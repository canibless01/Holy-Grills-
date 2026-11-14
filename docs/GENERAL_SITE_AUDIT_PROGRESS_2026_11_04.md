# General-site audit continuation — 4 November 2026

Current consolidated status: [reward restoration and remaining audit priorities — 11 November](REWARD_RESTORATION_AND_AUDIT_STATUS_2026_11_11.md). The lists below are chronological; later closure records supersede older “next” items.

Latest continuation: [menu performance, public crawling and settings checks](MENU_CRAWL_AND_SETTINGS_CHECK_2026_11_11.md). Event implementation is delegated to the other chat; the requested quick regression passed 114 event tests. Menu filtering after cache expiry no longer refetches the catalogue, and static/hydrated menu metadata agree.

Owner-requested brand continuation: [public brand representation and Google identity](PUBLIC_BRAND_AND_SEARCH_2026_11_11.md). Public story/FAQ/metadata now explain connection and campus participation, with mission/vision and verified business/review links. The internal founder document and commercial details remain unpublished. This is separate from the remaining role/settings/reporting audit.

The owner assigned the launch-remaining category to a new chat and this chat the remaining full-site A/B scope. Both use current main; fetch before every push. Do not reset genuine users/orders or replay old cleanup scripts. The uploaded UI skills collection remains deferred.

## Current completed batch

[Store / ingredient stock controls](ADMIN_STOCK_CONTROLS_EVIDENCE_2026_11_04.md): existing native create/purchase/usage/correction/ledger controls, campus changes, failed reads, response-loss replay, actual unit/cost/actor display, paging, normalized name duplicates and direct balance/ledger write protection are verified for the recorded cases. Backend 993 tests, browser, SQL rollback, typecheck/lint/build pass.

## Next general-site work

1. Stock reporting/reconciliation/export and wider low-stock notification delivery/retry behavior. Native metadata editing and archive/restore now have backend, browser and SQL rollback evidence; see [lifecycle closure](ADMIN_STOCK_LIFECYCLE_EVIDENCE_2026_11_05.md).
2. Remaining dashboard/analytics/economics/leaderboard/report filters, pagination, exports and arithmetic against controlled actions.
3. Review moderation and customer rating aggregation/reflection.
4. Remaining user/staff/profile/campus administration and native role/action matrix beyond completed reference-data batches.
5. Community manager/ambassador exceptional grants/share/measurement/report cases.
6. Remaining notification/newsletter administration and preferences; coordinate shared transport changes with the launch chat, which owns operational acceptance and recovery work.
7. Remaining system/settings/webhook controls and their consumers; full feature-flag consumer matrix; historical RPC/RLS/grant/schema-use review.
8. Remaining storefront edit/sort/concurrency/presentation variants; broad UI refinement remains deferred.
9. Disabled marketplace/subscription and broader catering/event management variants, coordinating with the launch chat for currently enabled events and shared payment/reward boundaries.

This list is not a statement that all these features are absent or broken. Existing A/B evidence remains valid; closure applies to the actual cases tested. The whole admin page-by-page audit is still incomplete. Launch acceptance stays with the other chat; current-source/deployment and live recipient/device confirmations should not be inferred from this stock-control batch.

## Ingredient metadata editing continuation

Added native name/threshold editing, a list refresh control, strict endpoint validation, own-campus/super-admin authorization, duplicate-name responses, atomic displayed-value comparison, and matching response-loss replay. Units, conversion, balance and ledger rows are never included in the update. This reuses existing columns and grants; no migration, new table or live-data mutation was needed.

Evidence and remaining verification are in [stock metadata editing](ADMIN_STOCK_METADATA_EDIT_EVIDENCE_2026_11_04.md). The launch chat's worker dependency fix `e704c5c` was integrated before testing. This closes the implementation and backend-contract part of metadata editing; it does not close archive/restore or the entire Store page.

## Ingredient lifecycle continuation — 5 November

[Archive/restore evidence](ADMIN_STOCK_LIFECYCLE_EVIDENCE_2026_11_05.md) closes the recorded native lifecycle cases and the preceding metadata browser verification. Balances/ledger are preserved, new archived adjustments are blocked, old receipts replay safely, stale intents cannot reverse newer transitions, and direct lifecycle writes are denied. The launch-chat milestone and check-in recovery changes from main were integrated; the final regression run passed 1,029 backend tests. Reporting and wider notification behavior remain open; this is not full Store or whole-admin sign-off.

## Reporting continuation — 5 November

[Reporting scope/date evidence](ADMIN_REPORTING_SCOPE_EVIDENCE_2026_11_05.md): fixed selected-campus Economics requests, stale replies, partial-failure presentation, recoverable date controls, WAT defaults, reversed/overflowing date validation and early export-limit validation. Native browser checks and 1,049 backend tests pass. Wider report arithmetic/exports and a new native stock reporting screen remain open. Live stock contains no ingredient records, so its zero-mismatch reconciliation is not counted as populated proof.

## Review and arithmetic continuation — 5 November

[Recorded review/report cases](ADMIN_REVIEWS_AND_REPORT_ARITHMETIC_2026_11_05.md): tier report activity is campus-scoped even when a member has other-campus history; controlled overview/redemption/tier arithmetic and multi-chunk reads are verified. Reviews now respects selected campus, resets/discards stale view state, uses stable page order and labels its average as page-specific. The rating fallback no longer weights a review repeatedly for repeated menu lines. Native review read/filter/detail/retry checks and 1,056 backend tests passed. Manual moderation writes, live public rating aggregation/reflection, wider refund/history/chart/export reporting and the remaining role/action pages are still open.

## Review follow-up closure — 5 November

[Follow-up evidence](ADMIN_REVIEW_FOLLOWUP_EVIDENCE_2026_11_05.md): native set/clear controls now use the existing flag field with campus checks, expected timestamps, response-loss replay and audit calls. Browser checks, 1,067 backend tests and fresh Supabase rollback role/public-average tests pass. Flagging does not remove scores or change HP. Public menu browser presentation remains separate; next is user/staff administration.

## User and grant continuation — 5 November

[Directory/grant evidence](ADMIN_USER_GRANT_CONTROLS_2026_11_05.md): fixed campus switching, failed history presentation, selected names across pages, single-grant identities and strict eligibility/values, preview/commit bulk identity reuse, partial-loss retry and explicit empty/null recipient safety. Backend 1,125 tests after notification-recovery integration, plus native controlled browser/real SQL rollback cases, pass. Manual expiry, wider recipient discovery and remaining role/identity cases are next; whole Users/HP coverage remains open.

## Manual expiry continuation — 5 November

[Expiry evidence](ADMIN_HP_EXPIRY_EVIDENCE_2026_11_05.md): native preview/confirmation and service-only ledger receipt support make partial/all-active administrative expiry safe across repeats, lost responses, changed balances and later earnings. Backend 1,161 tests, native browser checks and fresh Supabase rollback cases pass. Recipient discovery, wider staff/profile boundaries, scheduled expiry and remaining settings/feature consumers remain open.

## Owner-confirmed staff hierarchy — 7 November

[Community-manager account control](COMMUNITY_MANAGER_ACCOUNT_HIERARCHY_2026_11_07.md): campus admins may deactivate/reactivate their own community managers. The database already supported the intended hierarchy; API/UI restrictions were corrected, with no database restriction added. Cross-campus/admin-account protections remain. Backend 1,236 tests, native UI and fresh Supabase rollback cases pass.

## HP recipient discovery — 7 November

[Recipient-search evidence](ADMIN_HP_RECIPIENT_SEARCH_2026_11_07.md): single/bulk grants and manual expiry search the existing scoped directory beyond its initial page. Native browser tests prove stale-response isolation, failure/Retry, identity retention and empty-selection bulk safety. TypeScript and targeted ESLint pass; no database migration or real grants are involved. Remaining settings/consumer and wider staff/identity cases remain open.

## Webhook and database boundary — 7 November

[Database grant proof](EVENT_WEBHOOK_DATABASE_SECURITY_2026_11_07.md) removes browser table-maintenance and provider-payload write privileges while preserving scoped diagnostic reads and backend processing. [Native webhook controls](ADMIN_WEBHOOK_CONTROLS_2026_11_07.md) cover paging, WAT dates, scoped/stale reads, redaction, failed-read Retry and shared atomic replay claims. Full backend regression: 1,268 passed; browser/typecheck/lint/build pass. Event-management lifecycle and historical RPC review continue.

## Event operations and retained history — 7 November

[Event controls evidence](EVENT_MANAGEMENT_CONTROLS_2026_11_07.md): native paging/publication, WAT/funding inputs, locally rendered venue QR, attendee search/staff admission, read Retry, CSV defense, tier deactivation and receipt-based sales metrics now pass at mobile/desktop sizes. Direct issued-event/tier deletion is blocked by the database; two historical report RPCs now reject inactive admins. Backend 1,277 passed, native refund regressions and typecheck/lint/build pass. Organizer workspace/settlement is newly requested and next; cancellation/reschedule notices and broader exceptional cases remain separate.

## Organizer workspace completion — 8 November

[Organizer workspace evidence and use](EVENT_ORGANIZER_WORKSPACE_2026_11_08.md): subordinate role, own drafts/submission, private admin feedback/finalization, fixed per-tier settlement contracts, immutable ticket earnings, own statistics/search/QR/admission/export and manual payout request/approval/recorded-transfer loop are implemented. Mobile/desktop native journeys, real handler/middleware and fresh Supabase rollback cases pass; frontend typecheck/lint/build pass. Event-wide cancellation/reschedule notices, exceptional receipt recovery and device/bank acceptance remain separate; this is not whole-event, whole-admin or whole-database sign-off.

## Event reliability and storefront ordering — 9 November

[Independent-session evidence and fixes](EVENT_RELIABILITY_2026_11_09.md): simultaneous member/guest scans, process-exit rollback, committed-response replay, admission/refund races, payout reservation/replay and notification worker leases are verified on isolated PostgreSQL. Organizer notices now commit with the action using existing durable dispatch. Fresh Supabase rollback tests verify notification capture, equal-rank CMS/banner ordering and service-only permissions. Global super-admin uploads now pass the explicit-scope browser CORS preflight. Native ordering and event-image wiring checks pass; event exceptions are the next batch. Group/third-party ticket purchasing and HP sharing remain explicitly deferred.

## Student performance and wallet transfers — 9 November

[Performance/settings evidence](STUDENT_ADMIN_PERFORMANCE_2026_11_09.md) records immediate menu filtering, smaller responsive menu images, progressive admin/CMS feeds and settings/session isolation. [Wallet-transfer evidence and controls](WALLET_TRANSFERS_2026_11_09.md) adds the owner-requested same-campus cash transfer loop, atomic paired ledgers, owned receipts and recovery without new recurring jobs. These checks close the recorded cases; they do not imply that all historical audit items above or every first-page load have been certified.

## Ambassador reward interruption and concurrency — 9 November

[Grant reliability evidence](AMBASSADOR_GRANT_RELIABILITY_2026_11_09.md) closes the recorded lost-notice gap and a reproduced same-claim duplicate award. Grant/benefit and in-app/durable push now commit together; Python only wakes saved work. Issued/rejected/wrong-month milestone claims reject new grants while original receipts and explicit extra manual rewards remain supported. Independent local sessions verify duplicate/monthly/changed-config grant races, process-exit rollback, original-receipt replay, one dispatch lease, the last meal-discount use and concurrent restoration. Fresh Supabase grant and checkout/refund matrices pass with all fixtures rolled back. Wider promotion/reward/delivery combinations, reporting arithmetic, staff-action boundaries and complete settings/flag consumers remain open; this is not whole-site sign-off.

## Wallet recipient choices — 9 November

[Wallet lookup follow-up](WALLET_TRANSFERS_2026_11_09.md) adds owner-requested exact email/phone lookup alongside referral code. Normalized phone ambiguity refuses selection; account confirmation, same-campus restrictions, paired money movement and lost-response recovery are retained. Backend 1,436 tests, nine native wallet scenarios, original concurrency checks and both Supabase rollback matrices pass. This enhancement is separate from the open audit coverage groups above; those groups are not evidence that every listed area is broken.

## Wallet/funding reporting — 10 November

[Wallet & Funding](WALLET_FUNDING_ANALYTICS_2026_11_10.md) adds current customer-credit exposure, confirmed funding/activity, automatic plan/payment health and capped calendar projections, with super-admin accounts excluded throughout. One read-only aggregate, campus/role checks, date/CSV/retry/stale-response controls and no authorization exposure are verified. Backend 1,461 tests, seven native browser scenarios, typecheck/build and fresh Supabase rollback arithmetic/projection cases pass. Broader super-admin customer-test isolation and campus paid-order/cart alerts plus daily/weekly summaries are newly requested and next; the confirmed FUTA destination is grillthevibe@gmail.com.



## Event operations and customer QR — 10 November

[Event operations evidence and use](EVENT_OPERATIONS_2026_11_10.md): implemented admin-reviewed cancellation/rescheduling, transactional member/guest notices, preserved ticket/earning values, full unused ticket-amount refunds through existing wallet/provider paths, and safe handling of late/expired payments. Stale requests and direct lifecycle/date writes are guarded. Customer pages display actual private ticket QR images and avoid false unpaid/refund confirmations. Native, independent-session/process-exit and fresh Supabase rollback matrices pass for the recorded cases. Ticket resend/recovery, admission-opening configuration and live device/provider acceptance remain separate; this is not whole-admin/database sign-off.
## Campus operations, customer recovery and test-order scope — 10 November

[Implementation and evidence](CAMPUS_OPERATIONS_AND_RECOVERY_2026_11_10.md): private configurable operator recipients, paid-only order/cart alerts and concise WAT daily/weekly reports; atomic customer email/inbox/push recovery steps, truthful counters and payment/preparation stops. Server-derived super-admin test orders stay out of real fulfilment/capacity and customer reporting, while the test balance remains. Fresh production rollback and independent local-session checks pass. The newly reported cancelled-checkout recovery lock, rider multi-zone visibility/bulk assignment and kitchen/admin address visibility are the next work; they are not claimed closed here.

## Checkout restart, addresses and rider zones — 10 November

[Checkout/handoff evidence](CHECKOUT_AND_RIDER_HANDOFF_2026_11_10.md) closes the newly reported cancelled-payment recovery lock, hidden later rider zones, missing pre-assignment addresses and kitchen multi-batch rider assignment. An unpaid intent can be safely closed, including delayed creation; paid money/benefit restoration uses existing atomic rules. Kitchen/admin show saved addresses/pins, and riders see every returned active zone together. Full merged backend tests, native controls, production rollback money cases and an independent local creation/closure race are verified. These are bounded fixes, not a blanket certification of every historical audit group.


## Evening operational reporting — 10 November

[Updated timing and evidence](EVENING_REPORT_SCHEDULE_2026_11_10.md): owner-selected 21:00 WAT daily summaries, full 24-hour windows, thirty-minute staff cart alerts with send-time activity/payment checks, and cleaner operational emails. Existing dedupe, test exclusions, recipient controls and weekly calendar reports are preserved. Targeted backend/native/build and fresh production rollback cases pass; this does not change the remaining broader reward exception audit.

## Combined benefit restoration and menu-linked delivery — 11 November

[Evidence and consolidated remaining list](REWARD_RESTORATION_AND_AUDIT_STATUS_2026_11_11.md): fresh production rollback matrices pass campaign side/delivery/food-HP reservations plus promo/order-lock partial refund, changed campaign settings, final cancellation and retry conservation, alongside menu-linked physical reward kitchen/rider/delivery/unclaimed/refund paths. No new application defect was found in these cases. All fixture users rolled back; 43 targeted backend contracts pass. Exceptional event recovery, further reward/interruption combinations and remaining settings/role/reporting coverage remain separate.

## Squad combinations, recovery and retained revenue — 12 November

[New evidence and remaining limits](REWARD_COMBINATIONS_AND_REFUND_REPORTING_2026_11_12.md) closes the specified squad + earned physical reward + campaign + promo + lock partial-refund/cancellation combination, rejected-line conservation and isolated squad financial-recovery matrix. The real quote also covers squad food/delivery discounts with ambassador meal benefits. Corrected Economics/tier food revenue, card-origin refunds paid into wallets, location/demographic/source/calendar and item revenue, and refund-aware CSV fields. Controlled handlers, native scoped Economics and fresh production rollback matrices pass. No prices/orders/reward balances are rewritten, no provider sends and no schema change. Remaining populated stock reporting, legacy/interruption variants and settings/permissions are explicitly not counted as completed.

## Inventory, handover and staff settings loop — 12 November

[Closure evidence](STOCK_HANDOVER_SETTINGS_LOOP_2026_11_12.md): added read-only populated stock reconciliation/CSV, transactional low-stock episodes/outbox capture with restock re-arming and stale-send checks, atomic audit/inbox/push for three physical-prize families, preserved fulfilment timestamps, campus-aware feature gates and active-account legacy policy helpers. Full backend 1,650 tests, built native report/handover and existing stock suites, typecheck/build and three fresh production rollback matrices pass. No test fixtures remain or new periodic jobs were added. The separate legacy signup squad-share claim path is the next focused check; unrelated historical domains are not silently certified.

### 13 November — reserved squad signup HP claims

Closed cross-campus claim and award/marker/notice interruption gaps. Signup and the existing daily sweep share an atomic backend-only claim, preserve original grants across both legacy reference keys, and scope unowned invitation binding to the actual campus. No new job or session-hydration read. Full backend suite: 1,658 passed; production rollback and 24-request local concurrency proof passed; production fixtures remaining 0. See `PENDING_SQUAD_HP_RECOVERY_2026_11_13.md` for limits and evidence.

### 13 November — transactional check-in recovery notices

Attendance and its deterministic inbox/push receipt now commit together; replay matches old Python notice IDs, and the copy identifies the actual activity and WAT date. No new scheduled work. Expanded production rollback matrix and 81 targeted recovery/outbox cases passed; full merged backend suite **1,659 passed**. See `CHECKIN_NOTICE_RECOVERY_2026_11_13.md`. The preceding squad batch `5c5c7fa` has successful API/worker/beat/Vercel statuses.

### 13 November — membership milestone grant reliability

Replaced the unsafe read-before-award/no-reference anniversary path with an atomic account/milestone grant, monthly increment and inbox/push capture. Preserves original amounts after configuration changes, adopts exact legacy grants and their notice channels, supports current-month outage catch-up and month-end clamping, and retries incomplete recipients using the existing job. Full merged backend **1,665 passed**, final focused **24 passed**, production rollback and independent 24-session-request local matrix passed, no retained production fixtures. See `MEMBERSHIP_REWARD_RECOVERY_2026_11_13.md` for policy and scope limits.

### 13 November — visible checkout perks and gate-pickup communication

Owner-requested checkout tiles make free sides, delivery rewards and Food HP discoverable with focused dialogs and honest available/selected/loading/error states. Gate-only checkout now explains pickup in a popup and persistent summary; pinned home delivery is distinct and can explicitly switch to gate pickup. Existing quotes and reward/payment controls are retained. See `CHECKOUT_PERKS_AND_GATE_PICKUP_2026_11_13.md` for scope and verification.

Checkout UI verification: typecheck/full production build passed; all five new mobile/desktop reward/pickup browser cases and seven existing checkout/handoff regression cases passed. Native checks include selected reward IDs in quote requests, free-side Retry and pin-versus-gate transitions. No production database writes or real payments.

### 13 November — customer reminders for scheduled orders

Added transactional delivery-day customer reminders from 10:00 WAT through the existing scheduled scan and durable notification recovery. Members receive preferred inbox/push/email; guests receive email with their private tracking link. Paid/current/owner/date guards run again at provider handoff; repeated scans are idempotent, internal receipts stay out of status timelines and test orders are excluded. Fresh production rollback and targeted dispatcher/status checks pass. See `SCHEDULED_ORDER_CUSTOMER_REMINDERS_2026_11_13.md` for timing and evidence limits.

### 13 November — event recovery and database trigger grants

Closed event late-charge recovery into the app wallet, verified guest wallet-refund claims, verified guest attendance HP snapshot/review recovery, explicit recipient-bound durable ticket email resend and configurable admission opening times. The new event evidence is in `EVENT_WALLET_RECOVERY_2026_11_12.md`, `EVENT_GUEST_HP_RECOVERY_2026_11_13.md`, `EVENT_TICKET_RESEND_2026_11_13.md` and `EVENT_ADMISSION_WINDOW_2026_11_13.md`. Full backend suite reached **1,700 passed**; native guest/owner/admin controls, independent recovery/resend races, production builds and fresh live rollback matrices passed. Configurable opening remains optional for existing events and follows approved reschedules. No customer self-refund requests; new guest refunds wait for verified account linkage and stay in the app wallet.

Removed seven unnecessary browser EXECUTE grants from existing trigger helpers and verified real authenticated table protections still work. Every public table has RLS enabled. Advisor definer counts dropped from 13/22 to 6/15; predicates/aggregates/report grants are retained for dependency-aware review. See `DATABASE_TRIGGER_GRANTS_2026_11_13.md`. Remaining broader audit: historical RPC/RLS/schema dependency review and remaining native admin action/exception coverage (newsletter/preferences, ambassador reporting/share exceptions and CMS/presentation variants). The completed event feature batches are no longer open implementation work. Operational real inbox/device/provider/bank observations remain distinct from automated transaction evidence; deferred marketplace/subscription, group ticket purchases and official ticket transfer are not silently enabled.
### 13 November — atomic tier and grace transitions

Corrected rejected history event names, cross-campus tier selection and balance-driven ledger tier assignment. Tier/grace state, history and preferred notification receipts now commit together; missing-tier recovery and existing daily jobs use the same authority. Rolling refresh/grace scans use bounded DB batches instead of per-user REST ledger reads. Full backend 1,707 passed; fresh production tier and active/social/combined/squad reward matrices pass. See `TIER_GRACE_RECOVERY_2026_11_13.md` for migration history, tests and limits.

### 13 November — challenge/milestone and promotion verification

Closed the milestone completion-versus-notification interruption gap with receipt-backed SQL capture and post-commit wake only; pending cap periods now use WAT consistently. Fresh active/social milestone and combined/squad promotion-restoration SQL matrices pass, including idempotent grants and refunds after changed settings. Full merged backend suite **1,709 passed**. See `CHALLENGE_MILESTONE_PROMO_VERIFICATION_2026_11_13.md` for exact coverage and operational limits.

### 13 November — two checkout perk boxes and superseded tier notices

Combined delivery savings and food-HP selection under one Rewards tile beside Free sides, added clear cash-saving versus HP-multiplier explanations, and removed the empty delivery-zone info dropdown. Preserved exact location-based quotation and the ability to clear an expired reward when its quote fails. All six current perk/pickup cases and seven existing checkout/handoff cases pass; typecheck and full build pass. A final tier-notice guard skips recovered/superseded transitions before external handoff, verified in the production rollback matrix and dispatcher tests.

Final merged verification for this request: **1,736 full backend tests passed**, 13 checkout/handoff browser cases passed, native challenge progression and campaign editor/customer checks passed, typecheck/full production build passed, and fresh tier/milestone/promotion database rollback matrices passed. Current completed versus remaining scope is consolidated in `CURRENT_AUDIT_STATUS_2026_11_13.md`.

### 13 November — remove location-first reward friction

Rewards are now discovered and selectable before a location: delivery percentage/cap and food-HP multiplier appear upfront, selected IDs follow location changes, and exact savings come from the existing quote. Both types share one authenticated read-only discovery request; no reserve/spend action occurs. Full backend **1,753 passed**, typecheck/full build passed, and native selection/repricing/request-count checks passed. See `CHECKOUT_UPFRONT_REWARD_SELECTION_2026_11_13.md`. The owner assigned admin page-by-page work to the other auditor; it is not duplicated here.

### 13 November — legacy gift/reward recovery closed for current launch

Live read-only counts are zero for legacy gifts, flagged orders/lines, old profile multipliers/delivery caps and unsnapshotted redemptions. The obsolete hot-dog promotion remains disabled with an expired window. Added fresh isolated legacy admission/conversion/interruption/replay/new-gift/cancellation conservation proof; refreshed earned normal/flash snapshot proof using a self-created account. Both production matrices and 39 focused backend tests pass; all fixtures rolled back. No runtime/schema/customer-data change was needed. See `LEGACY_GIFT_RECOVERY_CLOSURE_2026_11_13.md` for exact closure and the separately deferred obsolete feature boundary.

### 14 November — signup/reference resilience and referral entry

[Recorded evidence](SIGNUP_REFERENCE_REFERRAL_RECOVERY_2026_11_14.md): short-lived campus reference snapshots, one bounded automatic transient read retry and reload reuse; direct signup referral/ambassador links plus backward-compatible guest root and /r entry. Native signup carries the prefilled code into the issued session. Existing referral and ambassador accounting remain separate consumers of the same unique code. No retained fixtures or external messages. CMS/storefront administration is the next requested continuation; this batch does not claim whole-site closure.

### 14 November — CMS recovery and database permission follow-up

[CMS evidence](CMS_EDIT_RECOVERY_2026_11_14.md): failed saves retain drafts, section/supporter/banner edits use row-version guards, supporter duplicate/delete recovery is visible, unrelated CMS work no longer loads newsletter feeds. Mobile/desktop native ordering/edit/retry and newsletter regression pass; fresh production rollback verifies CMS role/scope/version boundaries. Full backend 1,791 and full frontend build/type/lint pass. [Database evidence](DATABASE_PERMISSION_REVIEW_2026_11_14.md): all 15 remaining authenticated public definers inspected; fresh anonymous/student/admin/super-admin/inactive-helper matrix passes. Intentional helper/aggregate grants and backend-only no-policy tables retained. Managed extension/password-protection configuration and wider historical database inventory remain explicit; this is not whole-site sign-off.

Signup production follow-up: removed profile/cart reads from the pre-navigation success path, retained the destination's normal session restoration and bounded the single signup POST to 30 seconds. Root referral URLs use the existing CSR fallback because static Home is not their destination. The production-built mobile/desktop host check now redirects/prefills with zero hydration errors; ordinary public-page prerendering remains enabled. See the 14 November signup evidence.
