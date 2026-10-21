# Returning session recovery

The returning-user problem had several independent failure paths in code. Parallel requests each rotated the same expired refresh token. A late 401 could rotate again after another request had already recovered. `/auth/me` repeated Auth verification and then awaited optional wallet, welcome-credit and tier work. Finally, a temporary profile failure replaced the entire app with an account error, including the public storefront.

## Changes

- API requests share one refresh operation and reuse the current token for late responses from the expired token. Refresh failures retain the saved session; malformed responses fail explicitly. A rotation finishing after logout or a different sign-in cannot restore the old credentials.
- Browser restoration and login request `/auth/me?session=1`. The middleware still verifies the Auth identity and active application profile. The route reuses that verified identity, reads the full profile, and skips wallet, tier and welcome-credit work. Default `/auth/me` consumers retain balances/tier; tier lookup reuses the profile already read. An unavailable optional wallet returns `null`, not a fabricated balance or a failed identity.
- Authoritative wallet/HP reads run after profile hydration. Welcome-credit recovery uses authenticated `POST /auth/welcome-credit` once per loaded student per provider session; registration still attempts the immediate idempotent grant. The recovery endpoint uses the verified caller and ignores body-supplied user IDs.
- Restoration makes at most one automatic retry for network/5xx failures. A generation guard prevents an older restoration response replacing newer session state.
- A persistent profile outage leaves known public storefront pages visible with a compact retry notice. Private pages retain the account blocker until successful recovery. No cached profile is treated as authenticated identity.

## Verification

- `node scripts/test-session-refresh.mjs`: passed runtime cases for concurrent expired requests, late-401 token reuse, provider outage, malformed refresh reply and logout during rotation.
- `tests.test_welcome_credit`: 16 cases including session route boundaries, optional wallet outage and skipping optional balance/grant work. `tests.test_identity_completion`: four cases. Combined run: 20 passed.
- TypeScript validation and owned `HolyGrillContext.tsx` / `apiClient.ts` ESLint: passed.
- Controlled routed browser proof pending: `signup-welcome-20261021/session-browser.py`.
- Live dedicated recovery endpoint proof pending: `signup-welcome-20261021/verify-deferred.py`. It journals one owned audit fixture and performs no cleanup.

## Limits

No production latency measurement or real browser network trace is claimed. Server login and refresh still perform the existing synchronous streak check-in. Header identity styling and broader storefront loading are coordinated separately. No database migration or provider configuration change is required.
