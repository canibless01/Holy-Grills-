# Push device lifecycle — 26 November 2026

Provider reads recovered after the earlier approval-review usage errors. All 17 accounts skipped by the morning campaign now resolve to their correct external account identities in the connected OneSignal app. Sixteen currently have no active browser-push subscription; email subscriptions do not count as push eligibility. One now has an active browser subscription. Current state is not proof of what existed at the earlier send, so the historical skips are not relabelled as delivered.

The app had retained server device-token rows when the SDK subscription was disabled. It could also persist an assigned subscription ID during login before push opt-in. This made saved tokens look like reachable campaign recipients even when OneSignal could not deliver. Existing provider responses correctly marked those sends skipped, not sent.

The fix registers only an opted-in current subscription. On login/subscription change, a disabled current device is removed from this account's server token records. Opt-out and known subscription rotation use the same cleanup. Device writes are serialized so a delayed registration cannot finish after an opt-out deletion and restore stale eligibility. Stale identity generations are ignored; anonymous guests never call authenticated token endpoints. No browser/OS permission is granted automatically, account-wide preferences are unchanged, and other devices/accounts are preserved.

Added authenticated DELETE /auth/device-token with a token-only body, strict validation, rate limiting, explicit user/token filters and the existing owner RLS. Repeated removal is harmless. No new schema or migration. No historical token rows were bulk-deleted, no provider subscription was reassigned, and no extra message was sent.

Verification:
- Full backend suite: 2,192 passed.
- SDK contract checks: disabled assigned IDs, opt-in/revocation, delayed registration versus opt-out, known token rotation, guest/login/logout behavior and failure recovery pass.
- Real Supabase BEGIN/ROLLBACK fixture verifies owner-only revocation, another account's refusal, replay and preservation of other devices. All synthetic rows rolled back.
- Frontend typecheck, lint and complete production build pass. Corrected two pre-existing campaign editor API type arguments to use the actual non-generic API-client signature with explicit result typing.

Changes take effect as each browser runs the updated client and synchronizes its actual state. Do not silently enable notifications for the 16 accounts or count email-only subscriptions as push. Physical notification receipt was confirmed by the owner; its visual branding is the next requested fix and is not inferred from these lifecycle checks.
