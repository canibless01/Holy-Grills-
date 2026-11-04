# Ingredient metadata editing — 4 November 2026

## Result

The native Store cards now open an edit form for the ingredient name and low-stock threshold. The page has an explicit refresh action. The form keeps entered values after a failed response, prevents repeated writes while a request is pending, and displays the server's conflict/error message. All added copy is in the central message registry.

`PATCH /api/admin/stock-items/:id` accepts only name, non-negative finite numeric threshold, and the displayed original name/threshold. It uses the caller's user-scoped database client and checks modification rights. A campus admin cannot edit another campus's ingredient; a super admin can. Unknown/hidden rows and lookup outages preserve the existing 404/503 distinction.

The SQL UPDATE filters include both displayed values as well as the item ID. A competing edit between read and write therefore produces a 409 instead of silently overwriting it. A matching committed-response-loss retry returns the current row without writing again. A later different edit stays a conflict. Duplicate normalized names return a useful 409; database internals are not returned to the client.

Accounting fields are deliberately absent from the update and rejected if submitted: balance, campus, purchase unit, usage unit and conversion cannot be changed through this endpoint. Historical ledger entries remain intact. Existing authenticated column grants already permit only name/threshold updates. No schema change, migration or live data mutation was required.

## Verification

- Full backend regression: **1002 passed**, including the launch chat's Redis-transport compatibility tests. Seven additional backend contract tests cover successful conditional update, balance retention, matching retries, stale snapshots and zero-row concurrent losers, cross-campus denial/super-admin access, invalid/extra accounting fields and numeric edge cases, duplicate/database errors, and missing/unavailable lookup responses.
- The native Playwright suite now includes edited-value reflection, immediate repeated clicks, committed-response-loss retry, conflict preservation, and unchanged quantities/units/conversion/ledger assertions. These added browser cases are **not yet passed**: this execution environment denied Chromium's socket setup (`setsockopt: Operation not permitted`) before page interaction.
- TypeScript, ESLint, direct production client/SSR builds, and seven-route prerender passed. Full-build verification was attempted but the pipeline stopped at a subprocess permission error (`spawnSync esbuild EPERM`) in the existing canonical-origin test. This is not a completed full-build result.
- Existing stock SQL rollback evidence from the preceding batch still applies to the unchanged grants/ledger protections; no new live SQL proof is claimed for this endpoint.

## Still open

Native archive/restore, stock reporting/reconciliation/export, and execution of the added browser cases in an environment that permits Chromium. The full admin page-by-page audit remains open. Launch acceptance remains owned by the other chat.
