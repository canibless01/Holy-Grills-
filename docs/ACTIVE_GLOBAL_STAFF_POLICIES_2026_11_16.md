# Active staff global-policy boundaries — 16 November 2026

The wider A7 policy review reproduced a direct database write using a **fresh deactivated super-admin fixture with its existing authenticated identity**. An UPDATE to a global measurement unit changed one row. The transaction was rolled back. The API's active-account checks were already correct; five historical RLS policies independently read `profiles.role='super_admin'` without requiring the account to remain active.

Applied `20261115212822_active_staff_global_policy_boundaries.sql`: global academic calendar/levels/departments, brand partnership administration and measurement units now use the existing active `hg_is_campus_admin(NULL)` helper. The direct orders kitchen predicate also explicitly checks `is_active`. No new role, grant, table, price, account or customer record was introduced or changed. Existing active campus-admin brand permissions are preserved by their separate policies; own-campus academic management remains unchanged.

Fresh production rollback matrices pass: active super admin global edits; deactivated super admin denial across all five tables; student/global academic denial; active admin own versus foreign campus; and deactivating an initially active super admin while reusing the same JWT identity. Inactive global unit INSERT and DELETE are rejected too. The pre-existing settings/staff/helper matrices and the full paid order → kitchen → ready → rider handoff/delivery rollback journey also pass after the migration.

This closes the reproduced stale-token elevation. Public catalogue/measurement-unit reads remain public, and unrelated ownership policies are retained. No live account or genuine row was used as a mutation fixture.
