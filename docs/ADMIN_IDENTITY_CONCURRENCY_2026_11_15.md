# Staff/account editor concurrency — 15 November 2026

A3 follow-up closes selected-state/write races in role changes, activation and deactivation. These handlers previously authorized the selected profile but updated by ID alone. They now compare the role, campus and activation state checked during lookup in the actual UPDATE. Current UI requests also carry the displayed expected state. Conflicting state returns 409 with an explicit Refresh directory instruction; an already-achieved identical result remains a no-op replay.

The UI serializes role/access submissions, disables competing row actions while saving, prevents dismissal/change of a pending campus-role dialog or deactivation confirmation, and offers Refresh directory. Campus admins retain activation/deactivation authority over their own community managers. No new role-assignment authority, RLS policy, table, column or migration is added. Existing self/protected-account/campus guards remain.

Evidence:
- **33 focused identity/grant handler tests passed**, including 12 new concurrency/expected-state cases: stale displayed role, lookup→write races, malformed expected values, no repeated audit/notice/revocation on exact replay, super-admin demotion requiring a campus, manager account hierarchy and protected admin denial.
- Existing native Users/HP grant/expiry/search/role/hierarchy suite passes against current source.
- New native 393px/1280px controls pass: pending role lock, 409/Refresh/current-role retry, expected campus/active/role payloads, manager reactivation and guarded deactivation confirmation. No genuine account is altered.
- Actual handlers with independent sessions against disposable local PostgreSQL: competing role writes yield one winner and one 409; exact role retry does not repeat audit; eight matching deactivations produce one notification and one mocked revocation call. Local fixture profiles/Auth accounts/campus removed. This is local persistence-contract evidence using service-like access, not a replacement for live RLS/token-provider acceptance.
- Full backend **1,880 passed**; TypeScript, component lint, message/route contracts and complete production build pass. `liveApi.ts` is excluded by the repository's ESLint configuration, but is typechecked/built and exercised by native calls.

Limits: this protects the compared authorization state, not a new historical version counter for arbitrary intervening profile edits. Existing audit/notification/Auth cleanup delivery mechanisms are retained; process-loss durability/provider revocation acceptance is a shared operational follow-up. No permission bypass or genuine customer incident is claimed merely from the previous broad UPDATE shape. Wider remaining native/configuration/security work stays in the master record.
