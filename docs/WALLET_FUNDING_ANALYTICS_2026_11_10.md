# Wallet & Funding analytics — 10 November 2026

Admin → **Wallet & Funding** is a separate, lazy-loaded reporting view. It requests one aggregate when opened/refreshed or when a date range is applied; it does not add requests to student pages or poll the scheduler.

The view shows current outstanding customer wallet credit, funded-wallet/account counts, inactive-account credit, average funded balance, confirmed manual/automatic funding, refunds, other credits, wallet debits, internal transfer count/volume, automatic-plan states, all-time automatic contributions, pending/failed payment counts, and 7/30/90-day projections. Daily actual funding and the next 30 days of projected contributions are available, with a CSV download.

## Accounting and scope

- Accounts currently marked `super_admin` are excluded from every metric: balances, ledger activity, funding plans, attempts, projections and transfers. Transfers involving an excluded account are excluded from transfer volume. Non-super-admin staff accounts remain included, as requested.
- Current wallet credit comes from `wallets.balance`, rather than duplicated profile balances. Inactive customer accounts retain their outstanding credit; those balances are still obligations. Invalid/non-NGN balances are reported as reconciliation issues and excluded from the NGN amount.
- Confirmed funding means credited wallet value from Paystack card/bank top-ups. Automatic funding is a subset of this total, identified by its succeeded attempt/transaction link. Refunds and other credits are separate. Internal transfers count once and do not inflate funding or non-transfer wallet debits.
- This is a wallet-credit report, not a bank balance, PSP settlement or sales-revenue report. All-time automatic amounts use the plan counters updated atomically with confirmed funding.
- Balances use customers' current campuses; historical activity/plans use their recorded campuses. Campus admins are pinned to their own campus in middleware and SQL. Active super admins may choose one campus or all campuses. Students, kitchen/rider staff, community managers, event organizers and inactive admins cannot access the report.

## Projection rules

Estimates include only active plans with an active matching-campus owner, a reusable authorization on file, remaining contributions/time and no unresolved setup/payment attempt. They exclude draft, attention/paused, stopped, completed, inactive/moved-owner, missing-authorization, expired/exhausted and in-flight cases.

Windows cover the remaining part of today plus the following WAT calendar days: 7/30/90 days including today. Contribution frequency, remaining `stop_after` count and the exclusive end timestamp are enforced. One overdue contribution is estimated now; missed processing windows are never projected as a burst. Estimates assume subsequent payments succeed; they are separate from confirmed receipts. Reading the report never dispatches payments, changes plans or runs the funding state machine.

## Implementation and verification

Migration `20261110101325_wallet_funding_analytics` adds two reporting indexes and one `STABLE SECURITY INVOKER`, service-only aggregate. The backend verifies the actual actor and scope again in SQL, and returns only aggregates—no customer identifiers, authorization email, card token, card label or checkout URL. No new table, environment variable, recurring job or scheduler is required.

`tests/sql/wallet_funding_analytics.sql` passes locally and in Supabase with all fixtures rolled back. It tests exact money/category arithmetic, super-admin exclusion, legitimate other-campus/global deltas, inactive balances, confirmed versus pending payments, WAT midnight boundaries, three forecast windows, end/counter/frequency limits, overdue behavior, role/scope denials, no credential exposure and no plan mutation. Global assertions compare deltas against an unchanged repeatable-read baseline; genuine customer records are never reset or edited.

Backend regression: **1,461 passed**. Frontend typecheck and complete client/SSR/prerender build passed. Seven native browser scenarios cover mobile/desktop, apply-only date requests, CSV contents, initial failure/retry, stale snapshot labeling after refresh failure, malformed reports, campus-switch late-response isolation and manager denial. All report transport is mocked in browser tests. Production fixture-user and campus counts after rollback are zero. Security-advisor category counts are unchanged.

This exclusion applies to this new report. Broader super-admin test-order/analytics isolation and campus operational emails/reports are separately requested follow-up work; this release does not claim those are complete.
