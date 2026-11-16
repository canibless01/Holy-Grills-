# Spin-prize editor retry and concurrent edits — 16 November 2026

Prize-pool creation previously generated another row after a committed response was lost. The editor now reuses a stable request UUID as the existing prize primary key. An identical retry returns the original row; changed input or an already-edited row conflicts instead of overwriting it. No receipt table or migration was added.

Edits send the selected `updated_at`. The handler checks the selected version and conditions UPDATE on it; a competing update returns 409, while a retry of an already-committed identical edit recovers the saved result. Scope stays immutable and existing campus/global authorization is retained. Pending editor fields, repeated saves and close actions are blocked. Failed saves preserve the draft; a stale save offers an explicit Reload prize pool action.

Evidence:

- Native `scripts/test-admin-spin-pool-browser.py`: super admin at 393/1280px and campus admin at 393px pass. Read failure/Retry, global edit restriction, campus scope, all four category controls, committed/lost create response with identical retry, pending fields/close/duplicate guards, stale edit/draft/reload/new version and reload persistence. Controlled HTTP; no real prize/configuration mutation.
- 24 focused handler/typed-prize cases pass, including scope, intent validation, duplicate/conflicting creates, stale/identical edit recovery and lookup-to-write races.
- `tests/spin_pool_sessions.py`: actual handlers and eight independent disposable PostgreSQL sessions produce one row; competing edits have one winner and one conflict; identical edit retry succeeds and create retry never overwrites a later edit. Exact fixture cleanup. This proves local persistence contracts, not new live RLS/provider acceptance.
- Full merged backend **1,941 passed**. TypeScript, component lint and full production build pass.

No migration, privilege, actual spin credit/award, financial rule or earned reward snapshot changed. Other editor actions retain their existing evidence; this does not claim all reward administration is signed off.
