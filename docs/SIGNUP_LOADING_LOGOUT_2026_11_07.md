# Signup, ambassador activity and shared loading — 7 November 2026

Fixed the production rejection of Medicine and Surgery (MBBS): scalar PostgREST filters were adding literal quote characters to names containing parentheses. Scalar operators now preserve the name; IN-list grammar still escapes values. Signup sends the selected reference IDs and validates active rows within the chosen campus before creating an Auth account. Existing name/value clients remain supported.

Registration now loads campus, department and level options in one read-only database snapshot and HTTP request. It prefers campus overrides, excludes inactive/foreign-campus rows and supports retry. Public reference reads use short client caches; balances and orders remain live. Existing simultaneous-request sharing remains enabled across the application. Removed a duplicate initial streak read; session activity retains its subsequent streak refresh.

Ambassador Pending/Seen/Shared updates now apply the assignment-ID filter before the real database client's immediate update. Own-campus community managers and admins and super admins pass; another-campus community manager is rejected. Missing records return 404. The open assignment list updates in place without reloading the entire page. Failed assignment loads now have a retry action.

Admin/community-manager sections load on demand. The built Admin entry changed from 1,118,458 bytes (272,265 gzip) to about 38,500 bytes (11,700 gzip), approximately 96% less compressed entry JavaScript. Individual sections download when opened. This does not mean every complete page or its API data became 96% faster.

Logout uses one context transition, immediately clearing local identity and navigating to login while server revocation runs with a bounded deadline. Admin and public headers share it. Successful old-session JSON/CSV responses are rejected after logout/account changes, preventing late restoration of stale identity/balances. A delayed push-identity cleanup cannot detach a newer login.

The web Procfile keeps two worker processes and enables four threads per worker to reduce queues for I/O-bound requests across all roles. A custom Railway Start Command must not override the Procfile for this setting to take effect. No worker/beat schedule or reward arithmetic changed.

Validation:

- Backend suite passed before integration: 1,218 tests, including 12 new transport/snapshot tests. After integrating the latest main (including community-manager account controls), the full suite passed: 1,248 tests.
- TypeScript and complete production frontend build passed, including request-sharing, catalog cache, service worker and prerender checks.
- Controlled Chromium flows: guest selects MBBS and level, submits the selected IDs without creating a real account; community manager/admin/super-admin save Seen; student/kitchen/rider and all staff log out to login while the remote logout request is deliberately held. No browser runtime errors.
- Native SQL BEGIN/ROLLBACK verifies campus overrides, inactive-campus rejection, foreign-campus exclusion and service-only RPC permission. No fixture rows retained. No real users, orders or financial records changed.
- Existing security-advisor categories remain unchanged; new RPC is SECURITY INVOKER and executable only by service_role.

Scope limits: this verifies the reported community-manager status action and shared navigation, not every community-manager feature. Home/menu/dashboard/kitchen/rider API payloads and all real-device/network combinations have not been comprehensively benchmarked. Prior production parallel reference requests took about 15–17 seconds and one level request failed; this is a recorded sample, not a controlled performance percentile. Overall speed depends on actual Railway start configuration, database/network latency and the page's work.

Follow-up role-path review found the same immediate-update client misuse in existing ambassador reactivation/removal, monthly metric persistence, recommendation and admin decision writes, and the milestone-issued marker. Those calls now place their existing row filters before update. Role checks, grant issuance and reward amounts remain unchanged. Five additional real-client transport cases cover reactivation, removal, metric persistence, recommendation and decision; full backend suite: **1,253 passed**. This is additional coverage of these paths, not certification of every community-manager function. The repaired live read-only client also resolves the real MBBS row without creating an account.
