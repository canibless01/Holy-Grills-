# Database permission/dependency follow-up — 14 November 2026

Reviewed definitions, fixed search paths, browser execution grants and catalog dependencies for all 15 remaining public SECURITY DEFINER routines executable by authenticated clients. Six also have anonymous execution. These are not 21 separate functions. Retained intentional RLS/identity predicates, the public aggregate rating API and authorization-checked staff reports; blanket revocation would break live public/staff reads. Catalog dependency counts are supplemented by policy expressions/source consumers, since PL/pgSQL body references are not exhaustively recorded in pg_depend.

- The 11 identity/role/campus/squad/rider helper definitions are retained. Their outputs are self-identity, authorization predicates or a rider assignment restricted to the effective rider/authorized campus admin. Public campus visibility intentionally allows guest catalogue reads; the backend separately bounds its public campus queries. Helpers that authorize staff require the actual active profile; user-editable metadata is not an authority.
- `get_menu_item_review_stats` is the intentional public delivered-order rating/count aggregate used by menu reads; it does not return review bodies or customer identities.
- `get_hp_program_report_summary`, `get_pending_squad_hp_report` and `hg_hp_grant_segment` check the active database role/campus. Students and anonymous callers cannot obtain the staff reports/audiences; campus admins cannot request a foreign/global grant audience.
- `email_send_counters` and `newsletter_deliveries` intentionally have RLS with no public policies and **no anon/authenticated table grants**. They are backend bookkeeping, not missing customer features; no broad policy was added merely to silence an informational notice.
- Fresh inspection found zero public base tables with RLS disabled. All 16 public views readable by authenticated clients have `security_invoker=true`; none is anonymously readable. Anonymous/authenticated roles have no CREATE privilege on public.

Executed `tests/sql/public_helper_permissions_rollback.sql` on production: anonymous/student/campus-admin/super-admin/inactive-admin helper boundaries, own identity/campus, foreign/global report denial, public rating invocation and private bookkeeping grants pass. Fresh actors/campuses are entirely rolled back. No real provider calls, notices or customer rows were used. CMS mutation role/version checks are separately recorded in `CMS_EDIT_RECOVERY_2026_11_14.md`.

## Remaining configuration / limits

Advisors still report 2 no-policy informational tables, 1 extension placement warning, 6 anonymous/15 authenticated definer notices and leaked-password protection disabled. The intentional grants above remain visible in those advisor counts; this review does not represent them as new reproduced exploits or zero warnings.

`pg_net` reports `extrelocatable=false`. A casual ALTER EXTENSION SET SCHEMA is not a supported fix; rebuilding a managed extension requires dependency/job and hosting review. Its net-schema functions retain installed grants; this pass did not change those extension-owned permissions or prove alternate Data API schema exposure. Leaked-password protection remains a Supabase Auth configuration item, subject to the project's supported plan/configuration. No paid plan or provider change was made.

This closes the recorded public-helper grant/dependency check for the listed functions, not a blanket security certification of every historical schema object, every RLS policy, extension network behavior or unused-object deletion. Wider database inventory and the two configuration items remain explicitly open with the shared admin/security auditor.
