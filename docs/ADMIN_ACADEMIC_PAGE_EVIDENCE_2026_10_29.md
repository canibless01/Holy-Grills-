# Admin page-by-page audit: Departments & Academic Levels

This checkpoint executes the academic setup page's listed actions. It does not approve every admin page or every possible concurrent edit.

| Page action / boundary | Executed result |
| --- | --- |
| Load both tabs, empty lists, failed read and Retry | Native Chromium passes; failed reads are visible/retryable rather than guessed empty lists or an endless skeleton |
| Create department: name, faculty, optional slug, sort order | Required faculty validation, invalid-slug response, retained form fields, zero sort order and one write on a double-click pass |
| Edit existing department | Newly exposed Edit button saves name/faculty/slug/order; previously the editor's update branch had no entry button |
| Hide / restore department | One labelled visibility switch uses existing soft-delete/restore APIs; duplicate trash action removed; public active-list result verified in controlled HTTP and real RLS |
| Create/edit level: name, stored value, year rank, sort order | Native create/edit passes; negative rank refused without a request; rank/sort zero preserved; hide/restore passes |
| Search admin entries | Both tabs filter name/faculty/value and show a real no-match state |
| Selected campus / global | Fixed both backend admin lists to honor the super-admin campus selector, retaining global rows; non-super admins remain pinned to their own campus |
| Permissions | Native campus-admin controls do not offer global edits; super admin can. Actual authenticated SQL confirms own-campus changes, student/foreign/global mutation denial, cross-campus move refusal, and super-admin global/foreign superset |
| Profile propagation | Real department name/faculty and academic-level value updates reach the linked profile; existing database triggers, not a new parallel implementation |
| Duplicates / failure | Same-campus duplicate names refused by real existing unique indexes. API read outage returns 503; native write error keeps the modal. UI prevents concurrent clicks, but independent administrators still follow existing database last-write behavior |
| Faculty mapping | Public faculty listing now follows effective campus-over-global departments, preventing obsolete global faculty labels from appearing beside their replacements |

Evidence: `scripts/test-admin-academic-browser.py`, `tests/test_admin_academic_contract.py`, and real rolled-back `tests/sql/admin_academic_role_loop.sql`. The native browser uses controlled HTTP and issues no production writes; SQL uses isolated existing audit actors and rolls every fixture back. Full backend suite **742 passed**; frontend typecheck, changed-file lint and complete production build pass. No migration, new table, new grant or policy was needed.

## Owner-supplied FUTA additions

- Postgraduate is now a FUTA department under faculty/school **Postgraduate**, and a **PG** academic-level option. The original 51 departments remain: 52 total across 11 school labels. No 600 level was added. PG has a non-year rank of zero so it cannot accidentally satisfy the undergraduate graduation-year threshold merely by sorting after 500.
- Signup adds labelled school/department search fields while retaining native browseable dropdowns. Search is case-insensitive; clearing restores choices. The selected option stays mounted even when it does not match a new query, avoiding a displayed/saved value mismatch. Enter in a search field does not submit signup. School/campus changes clear dependent selections/searches.
- Mobile/desktop browser tests exercise all 52 options, school/department search, no matches, selection preservation, school/campus resets and outgoing PG department/level signup payload. No real Auth account was created.
- The existing FUTA semester start is now **26 October 2026**, following the owner's confirmation that session began this Monday. Its existing end date remains unconfirmed; no guessed end date or extra semester row was inserted.
- West/South/North gate names are owner-confirmed and all three already had stored coordinates. North's old pin was approximately one kilometre away from the published study reference. It is now **7.30707, 5.13978**, using [the 2024 FUTA Northgate traffic study](https://wjarr.com/sites/default/files/WJARR-2024-3109.pdf) (study area) and the matching OSM locality [as reproduced by Mapcarta](https://mapcarta.com/N4416374453). This is a published location reference, not a surveyed entrance pin. West and South's existing pins remain unverified: searches returned nearby areas/businesses rather than reliable entrance coordinates. No fee or pricing configuration changed.

Applied idempotent configuration DML: [Postgraduate/calendar/North Gate](data/configure-futa-postgraduate-calendar-gate.sql). No account/order cleanup was run.

Next page in this academic/setup group: **Academic Calendar**, including every modal field, scope selector, active/retired state and dated consumer. Delivery Gates/Hostels configuration follows. Their settings have targeted earlier evidence, but this checkpoint does not mark their complete native page actions finished.

A follow-up live Render `/api/departments` read in this checkpoint hit its 30-second read timeout before returning a response. Postgraduate/calendar/North Gate persistence is verified directly through Supabase; the timeout is retained as availability/startup evidence and is not presented as a successful deployed HTTP smoke. No root cause (cold start, deployment or upstream latency) is inferred from this single timeout.
