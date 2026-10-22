# Saved-session recovery and public storefront loading — 22 October 2026

Two concrete failure paths were present after the earlier hydration fix. Token login/rotation still waited for optional streak/database processing before returning new credentials; a slow streak path could outlast the browser timeout after Supabase had already rotated the refresh token. Meanwhile, public CMS requests attached the saved JWT, making every public carousel wait for Auth/profile verification and possibly token recovery.

## Changes

- Login returns issued credentials after confirming the active application profile. Refresh returns rotated credentials immediately after provider verification. Neither waits for streak processing.
- The authenticated `POST /auth/session-activity` records existing idempotent daily attendance after verified profile hydration. The browser requests it once per loaded account and refreshes the displayed streak afterward. Welcome-credit recovery remains a separate call. No arbitrary body-supplied user ID is accepted.
- The API client omits Authorization only on the explicit public storefront sections, banners, supporters, public configuration and flag GET routes. It retains the selected-campus display hint. Requests asking for inactive/management rows and all writes/private APIs retain authentication.
- Actual refresh rejection now clears only matching saved credentials and returns an authentication error instead of an endless retryable account-error loop. Network failures, provider 429 and 5xx retain the session and remain retryable. No cached profile is treated as authenticated identity.
- Sign-in persists across browser sessions by default. Explicitly disabling Remember me stores a `0` preference and uses session storage; the user can still choose session-only sign-in. Logout and actual revocation remain effective.
- Service-worker review found API responses are not cached; no cache-clearing workaround or provider/credential change was introduced.

## Verification

- Five new backend boundary tests plus existing welcome/identity tests: **25 passed**. They prove that login/refresh cannot invoke optional streak work before returning credentials, post-hydration activity uses the verified identity, and provider 429/5xx are not misclassified as invalid refresh credentials.
- Actual API-client runtime tests passed: one rotation for simultaneous/late 401s, retained transient outage/malformed-response state, logout/new-login races, public CMS header isolation, protected management reads and explicit persistence choice.
- Frontend TypeScript and owned-file ESLint passed.
- Parent ran `/workspace/work/ecosystem-audit/session-native-next.py` against actual frontend/backend/Supabase. Three cases passed: an intentionally invalid access token plus a real owned refresh token recovered through one real provider rotation while public CMS reads omitted JWT; reload preserved the verified account without another rotation; a new browser context restored the persisted local-storage session. Tokens/storage state are kept only in private chmod-600 scratch files. This did not create or delete customer data or use a fake payment/Auth provider.

This is functional recovery evidence, not a production latency measurement or proof that every host/device/network remains available. Sessions still expire or are revoked according to Supabase policy; a definitively rejected session must sign in again. No database migration was needed.
