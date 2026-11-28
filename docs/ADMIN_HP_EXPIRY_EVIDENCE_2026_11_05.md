# Previewed administrative HP expiry — 5 November 2026

Manual HP expiry now requires a fresh balance preview, a reason and an explicit confirmation showing the amount to remove. Blank amount means all active HP shown in that preview. Explicit amounts must be positive whole numbers within that balance. Editing the recipient/amount/reason invalidates the preview. Read failures or degraded balance data cannot produce a confirmable deduction.

The existing expiry API validates user/request identity, expected balance, amount and reason, resolves the target through the user's RLS client, and checks campus rights. A new service-only helper locks the profile, verifies the active staff actor and campus, checks/replays an existing ledger receipt before comparing current balance, and atomically writes the expiry and preview metadata into the existing HP ledger. No new table/column was introduced. There was no existing preview/idempotency helper for this administrative operation; the scheduled expiry service remains unchanged.

A matching retry returns the original removal and current balance; it cannot remove later earnings. Reusing an intent with changed terms fails. A stale preview fails without a debit, requiring a new preview/confirmation. The API records a best-effort admin audit entry only for a new expiry and refreshes the tier; a failed tier refresh is explicitly reported as pending. Audit/tier side effects are not claimed to be part of the atomic ledger transaction.

Applied migration **20261105121804_make_manual_hp_expiry_previewed_and_retry_safe.sql**, with that exact remote history version. One hg_admin_expire_hp signature exists; PUBLIC/anon/authenticated cannot execute it and service_role can. The function also checks the service role internally and validates the staff profile. Security advisors were inspected; this does not claim whole-database security closure.

Verification:

- **1,161 backend tests passed**, including twenty new expiry handler cases for preview/identity, scope, replay, strict values and clean database outcome mapping. This includes event-reservation and queued ticket-email changes from main through `800fce6`.
- **Native Chromium passed:** preview before confirmation, partial deduction, duplicate-click latch, committed-response-loss replay, preservation of later HP, stale-balance refusal, re-preview and explicit all-active confirmation, plus prior directory/grant/role/active/history cases.
- **Fresh Supabase BEGIN/ROLLBACK fixtures passed:** partial/all-mode removal, exact replay, changed payload rejection, later earnings preserved after either mode, stale previews refused, campus/student/inactive-actor restrictions, super-admin operation, receipt metadata and private grants. No actual customer account/balance was changed and no provider message was sent.
- TypeScript/ESLint and the complete production build passed, including client/SSR compilation and seven-route prerender.

Remaining: programme recipient search beyond the first loaded user list, wider staff/identity exceptional cases, scheduler-driven expiry semantics and reporting consumers. No whole HP programme/page or full admin audit closure is implied.
