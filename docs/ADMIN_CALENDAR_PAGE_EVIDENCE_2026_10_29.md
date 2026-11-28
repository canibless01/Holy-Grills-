# Admin page audit: Academic Calendar

Executed the page's six period types (semester, exam, break, holiday, orientation, graduation), every modal field, selected-campus/global creation, edit/scope, active/retired/restore, missing/reversed dates, missing academic year, failed save, failed load/Retry and double-click submission.

Fixed:
- All-campuses super-admin reads no longer inherit the admin's student-profile campus.
- A new super-admin period defaults to the selected header campus; explicitly choosing All Campuses still creates a global row.
- Campus admins have a pinned own-campus selector and payload, including profile-campus fallback, and are not offered edits to global/foreign periods.
- Current public period selection prefers a campus period over a newer overlapping global period.
- Save has an immediate duplicate-click guard; pending fields/close are locked, failed saves preserve inputs, dates and academic year validate consistently on create/edit.

Evidence:
- Native `scripts/test-admin-calendar-browser.py` passes for all six period types and listed fields/actions. Controlled HTTP only; no production write.
- Eight calendar handler contract tests pass for scope, current-period precedence, validation, retirement and access refusals.
- Real rolled-back `tests/sql/admin_calendar_consumer_loop.sql`: authenticated own-campus writes; fields persist; reversed dates/duplicate records refused; foreign/global/student writes denied; super-admin superset. Existing graduation consumer refuses semester-only and future-graduation periods; accepts an eligible final-year student during an inclusive current WAT graduation day; retirement disables it and restoration reenables it. The PG non-year option does not accidentally qualify. No graduation reward was claimed or credited.
- Full backend **750 passed**, frontend typecheck, changed-file lint and complete production build pass.

No new table, migration, policy, grant, scheduled worker, account or persistent audit fixture. The user's production semester dates/content were not changed in this batch. Existing independent-administrator edits retain normal database last-write semantics; this is not a claim that every possible race is version-checked.

Next: Gates/Hostels controls under Delivery → Zones & Fees, then the separate Delivery area page. The full admin audit remains open.
