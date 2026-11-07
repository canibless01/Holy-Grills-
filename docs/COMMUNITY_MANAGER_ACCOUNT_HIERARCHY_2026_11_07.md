# Community-manager account hierarchy — 7 November 2026

The owner clarified that campus admins control activation/deactivation of community managers within their own campus. The existing database permission was correct; the previous interpretation of it as a gap was incorrect. No database restriction or migration was added.

The admin API now includes community_manager among account statuses a campus admin may manage, enabling both deactivate and reactivate. Existing role-assignment policy is separate and unchanged. Cross-campus checks, self-deactivation protection, anonymized-account restrictions and super-admin-only control of admin/super-admin accounts remain in place.

The directory correctly enables community-manager activation/deactivation for campus admins and disables protected admin-account controls and self-deactivation. It no longer offers an admin-account action that the backend necessarily rejects.

Verification:

- **1,236 backend tests passed** against current main plus the pending manual-expiry batch, including ten new account-control cases for same-campus managers, foreign-campus denial, protected admin roles and super-admin scope.
- **Native Chromium passed** same-campus manager deactivation/reactivation and disabled admin-account controls, alongside directory/grant/expiry regression cases.
- **Fresh Supabase BEGIN/ROLLBACK fixtures passed** the existing database hierarchy: manager deactivate/reactivate allowed, foreign-campus/peer-admin/super-admin updates denied, manager self-profile display-name editing retained. No actual account was changed and no provider message was sent.
- TypeScript/ESLint passed. The complete production build passed, including client/SSR compilation and seven-route prerender.

This correction concerns account activation/deactivation; it does not grant campus admins global access or change the separate role-assignment rules. The wider ecosystem audit continues from the general-site progress document.
