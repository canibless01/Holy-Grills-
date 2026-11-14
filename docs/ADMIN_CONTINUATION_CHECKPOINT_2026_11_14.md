> Complete consolidated remaining list: [remaining work master](REMAINING_WORK_MASTER_2026_11_14.md). This supersedes earlier next-step/backlog wording; completed evidence remains valid.

# Admin continuation checkpoint — 14 November 2026

## Completed in this continuation

- Newsletter page controls, queue/cancel/replay and worker cancellation/unsubscribe/receipt/counter cases: `ADMIN_NEWSLETTER_PAGE_2026_11_13.md`, `ADMIN_NEWSLETTER_WORKER_2026_11_13.md`.
- Campaigns & Blasts composer/history/analytics/preview/test/sync/recovery and selected-campus authorization: `ADMIN_CAMPAIGNS_PAGE_2026_11_13.md`.
- Ambassador roster/search/tag retry, selected-campus scope, milestone create/edit/activation/financial limits/atomic receipts, independent-session concurrency, promo recipient/share/status failure/retry, monthly review identities and grant/recommendation controls: `ADMIN_AMBASSADOR_PAGES_2026_11_14.md`.
- Shared CMS draft/version/sort recovery and explicit reload: latest main's `CMS_EDIT_RECOVERY_2026_11_14.md` is integrated. Public returning-user Home/Menu recovery is rechecked: retained content during outage, automatic reconnect refresh, CMS edit invalidation, genuine empty results, explicit Retry, 13-second public cold read, definitive 401 without automatic retry, and stale cross-campus responses pass. The test now waits for Home's initial query to finish before counting retries; Menu and Home each mounting is not an automatic retry. Initial DOM readiness avoids waiting for unrelated blocked remote assets.
- Combined backend after integration: **1,797 passed**. New ambassador helper is applied once as migration `20261114140235`; live fixture/permission transactions roll back. Read-only catalog recheck: **136 public tables, 0 without RLS, 0 authenticated-readable views lacking security_invoker, 15 retained authenticated definer helpers, no anon/authenticated execution of the new milestone helper**. Direct anon/authenticated public-table TRUNCATE/TRIGGER/REFERENCES grants are absent. The seven broad-looking UPDATE predicates found by the scan are RESTRICTIVE parent/campus checks combined with separate ownership/admin policies; they were not converted into public write policies. Existing dependency/role evidence: `DATABASE_PERMISSION_REVIEW_2026_11_14.md`.

## What remains, without reopening superseded batches

1. Wider historical schema/object-use and policy-by-policy inventory beyond the public-helper/structural checks. No unused table is deleted merely because a source-text search finds no consumer. This is review breadth, not a newly reproduced customer defect.
2. Configuration decisions: managed non-relocatable pg_net extension placement and Supabase leaked-password protection. Neither was changed into a paid-plan/provider/extension rebuild as part of this audit. Intentional RLS/no-policy backend tables and authorization predicates are not errors to fix by opening public access.
3. Genuine operational observations: new scheduled-reminder inbox/device receipt, later nightly worker receipts, and payment/bank/provider settlement. Previous owner-confirmed install/GPS/push/ordinary ordering are retained as accepted evidence.
4. Broader optional UI refinement and combinatorial scenarios beyond the named native/API/SQL assertions. Existing stock/report/settings/event closures in `GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md` supersede the old October inventory. Inventory alone is never a full native pass.
5. Owner-deferred product work: marketplace/subscription expansion, group/buy-for-friend tickets, official ticket transfer, delegated door staff and a wider visual revamp. No new cron service, provider blast, customer-price edit or production fixture is introduced here.

The concrete ambassador/newsletter/campaign follow-up batch is complete for its documented cases. This is not an assertion that every possible action across all roles has been exercised or that every external provider delivered to a real device.
