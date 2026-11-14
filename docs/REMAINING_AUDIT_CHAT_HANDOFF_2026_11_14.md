# Parallel ownership and other-chat prompt — 14 November 2026

Use `REMAINING_WORK_MASTER_2026_11_14.md` as the shared backlog. This replaces the old A/B split for the remaining work; it does not reopen completed newsletter, blast, ambassador, CMS, stock or event batches.

| Owner | Remaining IDs | Scope |
|---|---|---|
| Existing admin-audit chat | A1, A2, A3, A5, A6 | Navigation/action matrix; reporting/leaderboard; native identity/campus/academic configuration exceptions; commerce/operations admin exceptions; public presentation/preferences. |
| Other chat | A4, A7, O4, O5 | Settings/System/feature-consumer verification; historical database policy/object/dependency/migration/grant review; password protection and managed pg_net review. |
| Coordinate operational evidence | O1–O3 | Real reminder receipt, later job receipts, provider settlement/failover. Other chat owns worker configuration/diagnostic observations under A4; this chat owns admin display/deep-link outcomes. Name the concrete acceptance case before running it so it is recorded once. Do not send duplicate blasts or payments. |
| Deferred | Master list's deferred section | Marketplace expansion, group tickets, transfer, delegated door staff, wide visual redesign, UI skills exploration and optional cleanup. |

## Copy to the other chat

Continue the Holy Grills remaining audit from the latest GitHub main in `canibless01/Holy-Grills-`, Supabase Test Two `zaxdkrmzyibkvlsrgmvq`. Read `docs/REMAINING_WORK_MASTER_2026_11_14.md`, `docs/REMAINING_AUDIT_CHAT_HANDOFF_2026_11_14.md`, `docs/DATABASE_PERMISSION_REVIEW_2026_11_14.md`, `docs/STOCK_HANDOVER_SETTINGS_LOOP_2026_11_12.md`, `docs/GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md` and the latest current checkpoint. Reconcile current main first; dated October inventories are historical.

You own **A4, A7, O4 and O5**:

1. **Settings/System and consumers:** complete a field/key-by-key verification of enabled settings, scopes, validation, persistence and the actual API/UI/job consumer. Verify uncovered native Settings/System diagnostic/manual-job controls, permission/failed-read/Retry/stale-write behavior and existing worker schedule/recovery status. The 17 feature flags already have tracing and targeted disabled-state evidence; preserve it and close only the uncovered consumer cases. No new external cron service is requested. Coordinate shared money/order/reward semantics before changing them.
2. **Database/security:** finish the wider historical RLS-policy/object/use/dependency/migration/signature/overload/duplicate-trigger/policy/index/grant review. Existing structural checks: 136 public tables all have RLS, authenticated-readable views use invoker security, no anon/authenticated TRUNCATE/TRIGGER/REFERENCES table grants, and the remaining 15 authenticated/6 anonymous definer helpers already have documented authorization/dependency checks. Newly applied `20261114140235_ambassador_milestone_write_intents` exists once and is service-only. Preserve intentional predicates, public rating aggregates and staff reports. A restrictive USING(true) parent check combined with an ownership/admin policy is not an unrestricted write. Do not delete schema objects merely because source search finds no use.
3. **Supabase configuration:** check leaked-password protection support under the current plan, and determine supported remediation/dependencies for the non-relocatable managed pg_net extension. Do not buy a plan, rebuild/drop the extension or change providers simply to remove an advisor notice. Explain unsupported configuration limits precisely.

The existing chat owns **A1/A2/A3/A5/A6**: admin navigation, report/leaderboard controls, identity/campus/academic UI exceptions, commerce/operations admin controls and public UI/preferences. Do not independently rebuild or claim those pages. Provider/job O1–O3 observations need coordination; record real receipt separately from database receipt/provider acceptance. Do not send users blasts or charge/refund customers as audit fixtures.

Use synthetic isolated fixtures, transaction rollback for live SQL, Cloudinary only for images, centralized `app/messages.py` copy and the existing brand. Do not delete genuine data, profiles, settings, menus, challenges or owner-authored storefront content. Keep secrets out of output/Git. Check schema reuse before adding objects; generate migration names with the CLI, apply once, verify actual live history/signatures/grants and duplicate objects.

Fix reproduced issues, verify UI→API→database→consumer with real roles/negative/retry/concurrency cases, and push in reviewable batches. Fetch/rebase current main normally before each push; never force-push or replace another chat's work. Keep the master list updated under your IDs with tested evidence and exact residual items. Return commits/migration names and any shared-contract change. No whole-site completion or numeric percentage from inventory/test count alone.
