# Event launch repairs — 10 November 2026

## Published batch 1

- Admin create keeps one UUID across unchanged failed-response retries. The event primary key enforces uniqueness; replay requires the same actor, campus and normalized request fingerprint. Changed input cannot reuse another request's receipt. No new database table.
- Edit submits editable fields only, preserving existing timestamp precision when the date input did not change. Nullable finance/read-only columns no longer break a capacity-only edit.
- Public list includes the image URL. Event detail renders its event independently of private ticket-history and tier reads. Description line breaks are preserved.
- Guests have an Events entry beside Sign In. Removed invented category chips; Discover/My Events remain.
- Organizer header/actions stay on one line within wrapping groups, with visible filled Retry controls.
- Offline recovery uses a cached first-party external script compatible with CSP, bypasses cached manifest data for its connection probe, and restores the original route on recovery.

Verification: 50 targeted backend tests; TypeScript; ESLint (one pre-existing unused savedEvent warning); PWA asset and service-worker checks; native admin browser matrix 360–1920px, including edit, upload, paging, QR, attendee search/admission and reports. Name-based organizer check-in verified at 393px and 1280px. Browser APIs are controlled fixtures; production network/provider acceptance is separate.

## Next batch in progress

- First-party signed email ticket artwork/viewer (Gmail strips inline data images).
- Registration-question editor and validation for admin/organizer/attendee loop.
- Free admission alongside optional paid support tiers; published readable event links.
- Recheck mobile organizer workspace, timeout retry and event loading with returning sessions.

Pending product decision: guest refund destination. Account refunds remain wallet; guest refunds keep the existing original-payment route until the user selects a different policy.
