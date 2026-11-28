# Analytics brand-request controls — 14 November 2026

Completed the brand-request input/status exception batch under A2. This feature logs data-sharing requests; approving a record does not itself send customer data to a partner.

- JSON is now edited as a draft. Previously each keystroke attempted to parse/reformat it, so incomplete edits were discarded and the previous object could be submitted. Invalid JSON, arrays/null and non-object values now produce a visible error; server validation also rejects non-finite and oversized JSON.
- Native required/email/length validation, accessible form/field labels and pending-state protection cover every current input. Cancel/backdrop cannot dismiss a pending create. A stable UUID survives a lost response; the existing table primary key stores the durable identity. Same-UUID retries return the original row, preserving later status, while different details conflict. No new table, column or migration.
- Approve/Reject submit the displayed expected status. A stale decision returns 409; the database UPDATE also compares the selected status/shared timestamp so a race after SELECT cannot overwrite the winner. Exact status replay does not write again. The UI serializes writes and provides Refresh requests for stale-row recovery.
- Existing admin/super-admin access and the current global record-keeping table are unchanged; this batch adds no data-export or provider permission.

Verification:
- **14 focused handler tests**: normalization, request replay, later-status preservation, changed payload conflicts, invalid fields/JSON/UUID, non-unique database failures, conditional updates, stale editors, exact retry and missing records.
- **1,811 full backend tests passed**.
- Real handlers against independent local PostgreSQL sessions: eight matching creates yield one row (one 201, seven 200); changed payload conflicts; competing approve/reject yields one winner and one 409; creation retry preserves the later status. The disposable local fixture is deleted. This uses the existing PK/conditional-update contract and does not claim a new live customer-role test.
- Native Chromium at 393px/1280px: invalid email/JSON, raw-draft retention, object payload, pending submit/cancel suppression, committed-response loss and same-intent retry, one saved row, stale decision/Refresh recovery, independent second request and successful rejection. No production write or external send.
- TypeScript, edited-component ESLint, message/route contracts and complete production build pass.

Remaining A2 is the wider reporting chart/filter/export/historical-attribution action matrix beyond recorded cases; the current brand editor/create/status controls are no longer an unfinished batch. A3 profile/account controls follow; Settings/System and broad database inventory remain with the other chat.
