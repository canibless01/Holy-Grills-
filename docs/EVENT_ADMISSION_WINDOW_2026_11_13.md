# Event admission opening — 13 November 2026

Completed: the admin event workspace has a check-in opening editor, separate from event cancellation/rescheduling. Configure 0–10,080 whole minutes before event start, or remove the opening restriction. Check-in always closes at event end. The public event page displays the saved opening in WAT. Campus admins manage their own campus; super admins manage any campus; organizers cannot alter the approved admission terms.

The existing event metadata stores one offset, not a new table/column. The offset follows event rescheduling automatically. Existing events keep their prior opening behavior until configured. Database admission enforces the time for both staff marking a ticket and venue QR self-check-in. Early attempts write no attendance/reward. A confirmed receipt remains idempotent, and settings lock after attendance begins or an event ends/is cancelled. Setting retries do not duplicate audits.

Applied migration: `20261113084207_event_admission_window.sql`. The admission function source fingerprint protects preceding HP/ownership/payment rules. Both the admission and settings functions remain backend-only invokers.

Verification: 1,700 backend tests; live BEGIN/ROLLBACK covering actual service-role configuration, organizer denial, early staff/self-scan rejection, rescheduled opening, normal admission/replay, post-attendance setting lock, event-end rejection and grants; Chromium at 393px/1280px covering required numeric limits, duplicate click, lost-response retry, saved public WAT display and clearing the restriction; TypeScript, edited-component ESLint and full production build. No real event was rescheduled or real ticket checked in.

Remaining: historical database/RLS/grant and enabled admin/settings action matrix, plus operational recipient/device/provider observations. Ticket recovery, late-charge wallet recovery and guest attendance HP now have separate completed evidence records.
