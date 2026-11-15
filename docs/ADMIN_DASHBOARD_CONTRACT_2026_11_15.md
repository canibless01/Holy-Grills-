# Dashboard API and failure recovery — 15 November 2026

Corrected a concrete response-consumer mismatch: `GET /analytics/dashboard` returns delivery windows, active batches and unassigned counts under `delivery_pipeline`; the screen previously read those keys at the root and showed zeros. The dashboard now reads the real nested shape, retaining older flat-response compatibility.

Reporting defaults use the Lagos business day, including the UTC hour before local midnight. Sales/users/items/HP receive the same inclusive 30-calendar-day range. HP previously used its own implicit backend default. Array-form HP tier distribution is now supported when the users report fails, rather than rendering array indexes with zero counts.

Initial failed order/HP/item feeds stay distinct from confirmed zero activity. Failed order charts stop showing permanent loading placeholders. Partial failure is an accessible alert with Retry, while a failed refresh retains previously loaded values. Manual refresh has an accessible label. New feedback copy is in `messages.py`.

Evidence:

- `scripts/test-admin-dashboard-browser.py`: seven native Chromium cases pass: populated mobile/desktop, all-feed failure/Retry, partial dashboard/HP/item failures and recovery, HP tier fallback, delayed campus-A response after switch to B, and manager denial with no report calls. Populated values reconcile the supplied API response to tiles/charts; all reporting requests use the same dates at 00:30 Lagos time. No report writes or real records/provider calls.
- 33 existing backend reporting/runtime/refund/scope regressions pass. Backend arithmetic was retained, not reimplemented.
- TypeScript, component ESLint and the full production contract/client/SSR/prerender build pass.

This establishes the listed response/render/recovery contracts. It does not establish a transactionally consistent snapshot across six separate API reads under concurrent production writes. Such a snapshot would require a separately agreed reporting contract; automatic refresh remains read-only.
