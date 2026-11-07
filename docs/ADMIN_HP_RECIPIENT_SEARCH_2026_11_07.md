# HP recipient discovery — 7 November 2026

The HP programme previously offered only its initially loaded users. Single grant, bulk recipient and manual deduction now search the existing campus-scoped directory by name, email or phone. No new endpoint, table or migration is introduced.

The reusable picker debounces requests, ignores superseded replies, provides visible failure/Retry and retains a selected identity after a grant refresh. Typing clears the selection; an empty selection cannot become an all-user bulk grant. All-user grants require the explicit existing all-active-users option. Pending writes disable recipient/amount/reason changes and intent reset.

## Verification

- Native Chromium/Playwright controlled HTTP suite (`scripts/test-admin-users-browser.py`) passed: email discovery beyond the initial 24 users; superseded replies; failed search/Retry; retained selected identity after refresh; empty bulk selection blocks preview; explicit recipient preview contains only that identity. Existing directory, scope, single/bulk grant, expiry replay and campus-admin community-manager controls also passed.
- TypeScript and targeted ESLint passed. Full production client/SSR build and all seven prerendered routes passed.
- After integrating the newer signup/ambassador main commits: 1,253 backend tests passed, and the native recipient/directory/grant/expiry browser suite passed again. This batch changes frontend controls and central copy only, with no backend behavior or database writes.

These are controlled browser checks, not live grants to real users or whole-admin sign-off. Provider/device launch acceptance remains with the launch audit.
