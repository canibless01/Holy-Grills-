# User directory and HP grant controls — 5 November 2026

## Fixed

The directory and HP programme page now pass the effective campus. Campus changes remount their workspaces, clearing prior drawers/selections and ignoring late directory replies; ordinary admins use their profile campus despite a stale stored selector. User list ordering includes the unique ID as a timestamp tie-breaker. Bulk selection retains selected users' display records across pages so the confirmation lists every chosen name.

Drawer history requests have a generation guard and a visible error/Retry state. Failed wallet/HP/order reads no longer look like an empty history. A successful drawer grant refreshes both the drawer's HP and the directory.

Single grants now require a UUID grant_id. The backend derives an actor-bound reference and reuses the existing atomic HP transaction business key. It validates whole positive amounts up to 100000, reason length, active target, self-grant denial and campus modification rights. Matching receipts return a replay without another credit/counter/audit call; conflicting details return 409. New grants disable event multipliers and return the persisted receipt's balance. Both frontend callers send a stable identity and block simultaneous submissions. The directory no longer promises unsupported negative deductions; its form clearly grants positive HP. The HP programme page has an explicit Start new grant control for deliberately repeating the same terms.

Bulk preview and commit reuse one grant ID, including retries after the old ten-minute fallback window. Directory bulk grants require a matching preview and reset it when terms change. The HP programme page also requires a matching preview for a commit. Partial/failed/previously applied/skipped recipient counts are shown honestly, and a retry retains the same identity. Empty explicit recipient arrays never fall through to an all-user segment; explicit null lists and fractional/non-finite amounts are refused.

## Verification

- **1,125 backend tests passed** after integrating notification recovery commit `92308cb`, including 21 new controller cases for identities, replay/conflicts, strict values, actor/campus restrictions, and empty/null recipient handling.
- **Native Chromium passed** directory campus/stale-response isolation, history failure/Retry, single grant validation/double-click/committed-response-loss retry, role and activation reflection, selected names across pages, required bulk preview, interrupted partial bulk retry without double-credit, regular-admin role choices, and the HP programme caller's grant identity/replay. Controlled HTTP only.
- **Fresh Supabase fixtures in BEGIN/ROLLBACK passed**: one identified admin grant credits once, matching replay does not credit again, a changed amount is refused, and actor/reason persist in the existing receipt. No real user balance/account was changed and no provider message was sent.
- TypeScript/ESLint passed. The final browser rerun completed without page errors on a stable source tree; an earlier run overlapped the Git rebase and reported development hot-reload context errors, so it was not used as acceptance. The complete integrated production build passed, including client/SSR compilation, prerequisite checks and seven-route prerender.

No migration, table or new privileged function was added. This uses the existing record_hp_transaction_atomic and its role grants. An older direct HTTP client must now send grant_id for a manual grant; both application callers have been updated.

## Remaining

The manual expiry/deduction route and its native loop, programme-page recipient discovery beyond its loaded list, wider user/staff exceptional role cases, and user deletion/identity lifecycle remain to audit. Generic audit-log durability and worker/provider notification recovery are separate platform concerns; existing best-effort logging/counter behavior is not newly claimed to be transactional. This batch is not whole Users/HP-page sign-off.
