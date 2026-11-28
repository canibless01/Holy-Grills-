# Event workspace presentation — 21 November 2026

The organizer workspace now has a branded control-room header, a compact scrolling event selector on mobile and a persistent event library on desktop, a selected-event overview with WAT date/venue/poster, clearly grouped actions, icon-led ticket counts, settlement grouping and direct links to overview/guest list/settlement. Empty workspaces explain how to begin. Existing account, review, payout, ticket and check-in requests are unchanged.

The shared admin header no longer offers both a panel-switch arrow and View Site for the same destination. One accessible student-site link works at every width. Kitchen/rider/event workspace switchers retain their own cross-workspace behavior.

Verification:
- Original organizer/admin native journey passes at 393/1280px: draft response-loss replay, submission, changes requested/edit/resubmit, agreed terms/publication, private earnings, venue QR, attendee search/admission replay/CSV, payout request replay/approval/recording, role/ownership denial and student-site navigation. Controlled HTTP only.
- `scripts/test-event-workspace-layout-browser.py` passes four width/role cases with eight events and a long event title: event section anchors, one create action, one student-site action, active event display and no document overflow. Screenshots inspected; transport fixtures use a synthetic event poster. No genuine event or payout was changed.
- TypeScript, component ESLint and full production contract/client/SSR/prerender build pass.

The next requested feature is separately gated store pickup, disabled by default. Per owner clarification it preserves preparing/ready, existing delivery/batch workflows and award-on-completion semantics. This UI batch does not pretend that the new pickup feature already exists.
