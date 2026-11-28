# Shared admin navigation — 14 November 2026

Found and fixed three shell defects during A1:

- Collapsed desktop navigation omitted grouped entries because group expansion was still required while the expansion buttons were hidden. Compact mode now exposes every permitted section icon.
- A remembered desktop collapse removed text labels from the mobile drawer. An open mobile drawer now uses its expanded presentation without overwriting the remembered desktop preference.
- Global search offered sections outside the user's role/workspace. Results now intersect role permissions with the current workspace's allowed IDs. An admin visiting the community workspace sees that workspace's three sections; the full admin workspace retains its own section results. Backend role checks and the route's allowed-section guard remain authoritative.

Added accessible close/expand/collapse labels using the central message registry. The existing URL selection, Escape closing and scroll locking are preserved.

Native controlled-transport test: `holy-grills-frontend/scripts/test-admin-navigation-browser.py`. It checks the 38-section registry's compact admin navigation, the three-entry manager navigation, remembered-collapse mobile labels, selection closing the drawer, Escape and close controls, role/workspace-filtered search, Enter navigation, reload/back/forward, forbidden section fallback and the student-page switcher. Roles/viewports: campus admin at 1280px, super admin at 393px, community manager at both widths. Admin visiting community workspace is included. No production write or real message.

This verifies the shared navigation shell and selected routes. It does not claim that the input fields/actions inside all 38 sections were exercised. The master backlog's action-level reconciliation and remaining individual page exceptions remain under A1/A2/A3/A5/A6.

Verification passed: all four native role/viewport cases, TypeScript, edited-component ESLint, message/route contracts and complete client/SSR/prerender production build. No backend or database authorization rule changed.
