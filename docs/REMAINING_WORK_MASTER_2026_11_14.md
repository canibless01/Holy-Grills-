# Remaining work — consolidated across both chats, 14 November 2026

Checked against GitHub main `8f47c0a`, the actual admin section registry, both current checkpoints and later closure evidence. This supersedes the old A/B split as a remaining-work list. Historical October “open” rows must not be treated as newly unfinished implementation.

**The complete admin page-by-page audit is not signed off.** Most core flows already have implementation and passing evidence. The list below records outstanding verification breadth, configuration/operational acceptance and deferred product work separately. An outstanding verification item is not evidence that its feature is broken. There is no evidence-based percentage completion: the total number of meaningful input/role/failure combinations has not been counted.

## Active audit work — this chat owns the remaining coverage

| ID | Area | Concrete remaining work | Existing work to retain |
|---|---|---|---|
| A1 | Shared admin navigation and workspace controls | Reconcile every current sidebar entry against its rendered page and tests; close uncovered mobile/desktop sidebar, search, direct-link, refresh/back, campus-switch and cross-workspace navigation cases; verify restricted roles cannot expose other sections. Publish an action-level coverage matrix instead of treating page inventory as approval. | Existing role guards, selected-campus remount, manager workspace and individual native page suites. |
| A2 | Dashboard, Analytics, HP Economics, Wallet & Funding, Delivery Costs, Leaderboard | Identify and run the remaining chart/filter/date/page/detail/CSV controls beyond recorded cases; reconcile populated figures with the producing records, especially historic/current-tier attribution and reports while underlying records change. Complete uncovered leaderboard/Hall-of-Fame administrative controls. | Scoped Economics/CSV, refund/net-food-revenue corrections, wallet funding projections, delivery-cost browser tests, populated stock reports, physical prize handover and scoped review/rating evidence. None is being rebuilt. |
| A3 | Users, profiles and staff/academic configuration | Finish uncovered native identity lifecycle and role-action exceptions: profile/avatar replace/remove, account deactivation/session behavior, competing role/account changes and the corresponding student/kitchen/rider/manager/organizer/admin/super-admin access. Reconcile campus, department/level and calendar controls with their latest tests so only uncovered actions remain. | Signup/reference/referral fixes; search/grants/expiry; campus-manager hierarchy; department, levels, calendar, gates/hostels and scoped configuration proofs. |
| A4 | Settings, System and feature consumers | Produce the final enabled-setting-to-consumer checklist; exercise uncovered native save/reload/invalid-value/permission controls and manual job/diagnostic actions. Separate effective settings from legacy/dead controls. Verify schedule/error/recovery reporting against actual existing worker behavior. | All 17 live feature names were traced; selected disabled gates, active-account helpers, operating-hours/calendar consumers, webhook diagnostics and settings merge/validation already pass. Do not reopen all 17 as unimplemented. |
| A5 | Remaining commerce/operations admin exceptions | Reconcile Orders, Wallet, Delivery, Order Locks, Promos, Abandoned Carts, Rewards, Free Credits, Spin, Challenges, Menu/Addons, Catering and Store against current native evidence. Run only remaining action/role/error/export exceptions not covered by the ordering, recovery, refund, fulfilment, campaign and stock closures. In particular, broader catering cancellation/communication variants and any newly added UI controls need explicit evidence. | Payment/order/batch/refund conservation, multi-gift combinations, physical rewards, rider/kitchen handover, menu inputs, stock lifecycle/reconciliation and original catering customer→admin→kitchen loop are implemented and tested for documented cases. This row is final action-matrix reconciliation, not a claim all those domains are unfinished. |
| A6 | Customer/public presentation and preferences | Close any unmatched requested presentation/field behavior found during final per-page reconciliation; check remaining notification-preference/deep-link and public rating/UI variants. Preserve owner-approved styling. Broader visual redesign is deferred below. | Cloudinary uploads owner-confirmed; newsletter/worker, blasts, ambassador roster/milestones/distribution/reviews, CMS edit/sort/version recovery and returning-user Home/Menu refresh now have current evidence. Those batches are closed. |
| A7 | Historical database/security inventory | Complete policy-by-policy and object/dependency/use review beyond the structural and public-helper checks; reconcile migration signatures/overloads, duplicate policies/triggers/indexes and service/browser grants. Any obsolete object requires dependency proof before removal. Record intentional exceptions. | All 136 public tables have RLS; readable views use invoker security; browser maintenance privileges removed; remaining 15 authenticated/6 anonymous definer helpers reviewed; milestone helper service-only; latest migration appears once. Advisor warnings do not imply all these protections are absent. |

### Next execution order

A1 navigation/action coverage → A2 reporting/leaderboard gaps → A3 identity/configuration exceptions → A4 settings/system consumers → uncovered A5/A6 actions → A7 remaining object/policy inventory. Fix reproduced defects and push in batches. Existing passing cases remain regression anchors. New findings will be added under their ID rather than silently expanding the backlog.

## Configuration decisions / operational acceptance

| ID | Item | Remaining acceptance |
|---|---|---|
| O1 | Scheduled customer reminders | Observe a real new scheduled-reminder email/push on the customer's inbox/device and its correct private destination. Stored receipts and provider acceptance are already separately tested. |
| O2 | Existing periodic workers | Observe later nightly/scheduled job receipts and recovery after a real worker interruption, confirming the deployed worker/beat or agreed external scheduling arrangement actually runs. No new cron provider is authorized by this list. |
| O3 | Payment/email/push provider operations | Retain prior accepted ordinary ordering/push/install/GPS tests; record any still-unobserved bank/provider settlement and actual production failover/quota behavior. Controlled quota/retry/counter proofs are already implemented. This is not a request to charge customers or blast recipients. |
| O4 | Supabase leaked-password protection | Confirm supported plan/configuration and enable if appropriate within the existing plan; report a plan restriction if applicable. This is Auth configuration, not a missing custom password-reset implementation. |
| O5 | Managed pg_net placement | Record hosting-supported remediation/dependency implications for this non-relocatable extension. Do not drop/rebuild it merely to clear an advisor warning. |

No outstanding newly reproduced launch-blocking code defect is recorded in the current two checkpoints. That does **not** certify the remaining untested cases or replace the operational checks above. Newly reproduced blockers take precedence over the sequence.

## Deferred product work — not part of launch completion

- Marketplace/peer-trade and subscription/code expansion beyond the existing released/gated features; automatic wallet funding is already implemented and is not this deferred category.
- Group/buy-for-friend event tickets and shared HP.
- Official ticket ownership transfer.
- Delegated event door-staff assignments.
- Broad UI redesign, including further spin/leaderboard/presentation polish beyond functional fixes.
- Exploration of the user-uploaded UI skills folder.
- Optional obsolete-schema deletion/large data cleanup, requiring an explicit reviewed inventory; no genuine profiles, orders or owner-authored menu/reward/storefront settings are deleted by this audit list.

## Closed follow-up batches — do not keep listing as unfinished

- Newsletter controls and durable worker send/cancel/unsubscribe/counter boundaries.
- Campaigns & Blasts editor/history/analytics/test/sync/recovery and scoped access.
- Ambassador roster, milestone configuration/edit/activation, atomic request replay, distribution/share/status and monthly review/grant controls.
- CMS failed-save draft retention, versioned edits, sorting/reload recovery; returning-user storefront revalidation and campus-cache isolation.
- Current legacy reward recovery; tier/grace transitions; challenge/milestone recovery; scheduled reminder implementation; multi-gift/reward/refund recorded combinations.
- Event owner workspace, settlement contracts, registration/payment/check-in recovery, guest QR/account linking and administrator-only wallet refunds for the documented cases. Deferred event additions are listed above.

Evidence index: `ADMIN_AUDIT_COVERAGE_STATUS.md`, `GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md`, `ADMIN_CONTINUATION_CHECKPOINT_2026_11_14.md`, `CURRENT_AUDIT_STATUS_2026_11_13.md`. The latest combined backend checkpoint is 1,797 passing tests and a passing production build. Neither a passing count nor a working page URL is whole-site sign-off.
