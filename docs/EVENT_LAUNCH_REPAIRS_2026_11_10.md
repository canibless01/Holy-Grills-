# Event launch repairs — 10 November 2026

## Published batch 1

- Admin create keeps one UUID across unchanged failed-response retries. The event primary key enforces uniqueness; replay requires the same actor, campus and normalized request fingerprint. Changed input cannot reuse another request's receipt. No new database table.
- Edit submits editable fields only, preserving existing timestamp precision when the date input did not change. Nullable finance/read-only columns no longer break a capacity-only edit.
- Public list includes the image URL. Event detail renders its event independently of private ticket-history and tier reads. Description line breaks are preserved.
- Guests have an Events entry beside Sign In. Removed invented category chips; Discover/My Events remain.
- Organizer header/actions stay on one line within wrapping groups, with visible filled Retry controls.
- Offline recovery uses a cached first-party external script compatible with CSP, bypasses cached manifest data for its connection probe, and restores the original route on recovery.

Verification: 50 targeted backend tests; TypeScript; ESLint (one pre-existing unused savedEvent warning); PWA asset and service-worker checks; native admin browser matrix 360–1920px, including edit, upload, paging, QR, attendee search/admission and reports. Name-based organizer check-in verified at 393px and 1280px. Browser APIs are controlled fixtures; production network/provider acceptance is separate.

## Completed batch 2

- Replaced email data images with a signed first-party PNG URL and a View ticket and QR button. The fragment-based viewer opens for guests without a session. Tokens bind event, ticket and recipient; no third-party QR service, public Cloudinary upload, or email-address-only ticket lookup. Ownership/payment/cancellation/expiry checks run before QR artwork or PDF is issued.
- Shared admin/organizer registration-question editor: short/long answer, dropdown, radio, multiple choices, confirmation checkbox, date, email and number; bounded definitions and server-side required/type/choice validation. Answers are retained on tickets, shown in the organizer roster and exported. Reused events.registration_fields and ticket metadata.
- Free admission and optional paid support tiers work together. Attendees choose one tier; a paid support choice starts payment rather than issuing a free ticket. Free/paid ticket confirmations now use the same QR/PDF/signup controls. Existing one-ticket-per-attendee policy remains; this is not an additional donation after already booking.
- Existing UUID event links still work; readable event slugs now resolve publicly and organizers can copy their canonical event link. Old generated organizer-UUID slugs were replaced; intentionally authored slugs were preserved.
- Organized the workspace header into identity and navigation rows, kept actions on one line, and made retries visible. Public event reads skip saved-session Auth verification; event content renders before private ticket history and ticket options. Registration waits for ticket options and shows an explicit retry if they fail. Attendance count now uses a single indexed join rather than downloading attendee IDs.
- Corrected two signup reconciliation paths which previously linked guest tickets before email confirmation. Reconciliation now requires the Auth-confirmed email and active profile, excludes already checked-in bookings, and does not transfer another account’s ticket. A private bounded verified-email helper avoids granting the service role broad SELECT access to auth.users.
- Allowed the application’s own camera in the generated production Permissions-Policy, so QR scanning is not blocked at the hosting policy layer.

Pending product decision: guest refund destination. Account refunds remain wallet; guest refunds keep the existing original-payment route until the user selects a different policy.


## Verification for batch 2

- Full backend suite: 1,555 passed before the final PDF guard; the final QR/PDF/management/operations subset then passed 53 tests (including signed PDF output and refusal for pending/refunded tickets). New question-validation, retry and signature-tampering cases are included.
- Native Chromium at 393px and 1280px: admin create response-loss replay, capacity-only edit, question creation/options, guest answers, free ticket confirmation, optional paid-support gateway navigation, friendly slug resolution, preserved paragraphs, email token forwarding/QR viewing, signup prompt and failed-read retry.
- Existing customer QR browser regression passed mobile/desktop: actual PNG decoding, owned and guest identity, failed QR retry, paid/unpaid/refund states and door check-in.
- Existing organizer native journey passed mobile/desktop: draft response-loss replay, review/changes/resubmission, admin terms and publication, attendee lookup/check-in, CSV, payout request replay/approval/recording and role boundaries.
- Offline Retry tested in Chromium under a policy that blocks inline JavaScript: failed probe resets the button; subsequent successful network probe reloads.
- Supabase migration history: `20261110202333_event_registration_questions_and_verified_claim` and `20261110202603_event_verified_identity_reader`. Rehearsed on an isolated Postgres clone, then tested on Supabase inside BEGIN/ROLLBACK with fresh synthetic identities. The verified-link operation also ran under SET ROLE service_role. Browser roles cannot execute the new helpers; existing organizer helper signatures/grants are unchanged. No new table was created.
- Security advisor categories match the pre-existing baseline. This batch does not certify unrelated database advisor findings as resolved.

## Remaining verification / boundaries

- A newly issued real email should still be opened on Gmail and its ticket scanned on a handset after deployment. Provider inbox/image-proxy/device acceptance was not simulated as a live success; browser and backend requests above were controlled, and no real audience blast or payment was sent.
- Already sent/frozen outbox emails retain their original content; no blind resend was performed. A customer can still be admitted by organizer name lookup.
- The signup prompt promises HP when an account holder attends. Retroactive HP recovery for a guest who already checked in before creating/verifying an account is not added by this batch; those tickets are deliberately excluded from automatic ownership reconciliation.
- The larger design-reference revamp, group purchases and official ticket ownership transfer remain outside this urgent repair batch. Manual name lookup and once-only admission remain available.


Final integration: preserved the newer evening-report, cart-recovery and menu-reward changes from main. Production client/SSR builds passed after integration; 145 targeted backend tests passed on the integrated code. A final guard also keeps registration disabled until an authenticated visitor's existing tickets have been checked, so a slow ownership/linking read cannot invite a second booking. Failed ownership reads provide an explicit Retry instead of presenting a new checkout.
