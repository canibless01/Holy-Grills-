# FUTA department catalogue and signup

The user's 51 department names and ten school/faculty labels are now stored under **FUTA Main Campus** (`futa-main`). The existing departments table already has a `faculty` field; signup and profile services derive the canonical faculty from the selected department. No faculty table, new API, schema migration, grant or policy was needed.

Source: [51 supplied rows](data/futa-departments-2026-10-29.tsv). Applied configuration: [campus-scoped upsert](data/upsert-futa-departments.sql). It resolves the existing campus by slug and updates same-campus names on repeat. Existing global defaults are retained for their existing references and other campuses. The public endpoint prefers FUTA rows over matching global names: the executed live anonymous request returned exactly 51 unique names with exactly the supplied faculty mappings. Existing FUTA profile faculty text was aligned to that mapping without replacing profile department IDs.

Signup now asks for **School / faculty**, then shows only that school's departments alphabetically. Changing school or campus clears the previous department. All ten schools and 51 options were exercised in controlled Chromium at mobile and desktop widths. The outgoing signup request retains the canonical department name; the client does not choose its persisted faculty.

Validation:
- Live anonymous backend `/api/departments` for FUTA: 51/51 names and school mappings match; no duplicate names.
- `scripts/test-signup-faculty-browser.py`: mobile/desktop, all ten schools, all 51 options, required school, changing school/campus, canonical outgoing department, no Auth writes.
- Existing signup/scheduling browser regression passes: missing birthday, optional consent, reference retry, full/closed/capacity dates and ambassador admin screens. Its old mobile-only hidden-header assertion was corrected to assert the visible promotional-message action.
- Full backend: **732 passed**. Frontend typecheck, changed-page lint and full production build pass.

No account was created or deleted for this batch. The separate [reset preparation](PRE_LAUNCH_CLEANUP_PLAN_2026_10_29.md) records current Auth/profile counts and reference-data questions. Website deployment completion is not inferred from a successful Git push; the department data is already verified through the live backend.
