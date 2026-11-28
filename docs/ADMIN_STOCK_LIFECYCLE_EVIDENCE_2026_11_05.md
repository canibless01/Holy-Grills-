# Ingredient archive and restore — 5 November 2026

## Result

Store now has Active ingredients and Archived ingredients views. Each ingredient can be archived after a confirmation explaining that purchases/usage stop while balance and ledger remain available. Archived cards retain their name, balance, metadata editor and ledger; operational purchase/usage controls are hidden. Restore returns the same ingredient to active use. Adding an ingredient from either view returns to the active list.

The list endpoint supports validated `state=active|archived|all`, defaulting to active for existing callers. The native page requests all rows for its selected campus, filters locally, and excludes archived ingredients from active balance/low-stock summary tiles. Campus switching still remounts the workspace and drops prior modal/list state.

## Database and permissions

Applied migration **20261104213720_add_reversible_ingredient_stock_lifecycle.sql**, using the actual remote migration-history version. This adds `archived_at` and `lifecycle_version` to the existing stock row; no new table or ledger type. The nullable timestamp stores archive state, and the UUID identifies the last lifecycle intent so an old request cannot reverse a later archive/restore.

One private `hg_set_stock_archived(uuid,boolean,uuid,uuid,uuid)` helper locks the ingredient row and checks the actor's active profile and campus role. It compares the expected lifecycle version and recognizes a matching response-loss retry. Changed-payload or stale requests fail. It does not delete, zero, convert or recreate accounting rows.

The single existing `hg_adjust_stock_balance` signature is retained. Its row lock serializes adjustments with lifecycle transitions. Receipt replay remains before the new archived-state rejection: an already-recorded purchase may be retried after archive without posting again, while new purchase/usage/waste/correction entries fail with restore guidance.

Both routines have exactly one overload and are executable by service_role only, with PUBLIC/anon/authenticated access revoked. The backend resolves the item through user-scoped RLS, checks modification rights, and passes the authenticated actor to the service call. Clients cannot supply an actor. Direct INSERT is restricted to the original create fields; direct UPDATE remains name/threshold only. Browsers cannot set lifecycle state/version, modify balances, delete ingredients, or write ledger entries.

## Verification

- **1,029 backend tests passed**, including seven new list/lifecycle/permission/error contract tests and the other chat's atomic milestone work and check-in recovery commit `2e90961` integrated from main.
- **Native Chromium/Playwright passed**, with controlled HTTP and no live writes: active/archived views, confirmation copy, repeated-click latch, archive and restore committed-response-loss retries, conflict retention, hidden operational controls, preserved units/balance/ledger, archived ledger access, campus/stale-response isolation, and prior metadata-edit cases.
- **Supabase SQL rollback passed** using only fresh synthetic campuses/actors/items inside BEGIN/ROLLBACK: unchanged balance/ledger across archive and restore, old purchase receipt replay, all four new adjustment types blocked while archived, stale and changed-payload lifecycle rejection, student/cross-campus denial, new purchases after restore, direct browser lifecycle writes denied, and private function grants. No customer account/order was changed and no provider notification was sent.
- Migration history contains one matching entry; the adjustment and lifecycle routines each have one signature and correct role grants. No duplicate table or alternate adjustment helper was introduced.
- TypeScript/ESLint and the complete production build passed, including client/SSR compilation, prerequisite script checks and seven-route prerender.

Security advisors were inspected. Neither stock routine is listed as publicly executable. Broader pre-existing findings remain in the general-site schema/security review: [public function execution](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated function execution](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), [extension placement](https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public), and [Auth password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). This batch does not claim whole-database security sign-off.

## Remaining Store scope

Reporting/reconciliation/export, wider low-stock notification delivery/retry behavior, and any broader stock workflow requirements beyond these recorded lifecycle cases. Full admin page-by-page coverage remains open. Launch acceptance remains with the other chat.
