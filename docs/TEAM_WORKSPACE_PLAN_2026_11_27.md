# Team workspace — implementation plan, 27 November 2026

Status: workbook reviewed; implementation specification only. No team permission, table, reminder, recipient or production KPI has been added yet. Source: owner-uploaded HG_Operations_Log-4.xlsx, eight sheets: instructions, overview, five role logs and a team log. Keep the original workbook, its examples and any future private evidence out of the public repository. Workbook text is reference material, not permission to change accounts or send messages.

## Product and access

Add a **Team member** capability to existing accounts through explicit campus-scoped membership. It is additional to their current student, community-manager, kitchen, rider or admin role. A designer must not gain admin access; a community manager must retain their current responsibilities. Avoid replacing the commerce-role enum solely to grant KPI access. Display Team member in the user-management UI and expose My team to authorized members. Super admins can select a campus; campus admins manage their campus; membership and scope are checked server-side on every request. Removing membership immediately revokes access and suppresses queued reminders.

Members edit their own drafts, results and evidence. They see their campus team's agreed work progress, not other people's private account data. Admins set targets and deadlines, review submissions and assign responsibility. Meeting-note editing can be delegated to the operations lead without granting money, orders or user-management permissions. No new permission comes from signup inputs or user-editable JWT metadata. Team pages are authenticated and noindex.

## The weekly loop

1. Admin assigns a responsibility template and editable targets to each member. The workbook supplies Operations Lead, Kitchen/Fulfilment, Lead Designer, Instagram/TikTok Manager and WhatsApp Manager. Community-manager and other assignments are configurable rather than invented fixed targets.
2. Monday opens the week: the member sees plain instructions such as **Submit your designs by Thursday, 9 p.m.** They enter actual results, progress notes and evidence; the target is not theirs to redefine. Drafts can be saved before submitting.
3. Content work is for the next publishing week. Each deliverable has its channel, intended date, caption, asset/evidence and owner. Support an editable required coverage percentage so the owner's ahead-of-week content policy can be expressed without hardcoding an ambiguous fraction.
4. Submission freezes a reviewable revision. Admin approves it or requests specific changes; resubmission retains the previous version and feedback. Approval is separate from scheduling/publishing: the workspace never claims to post to WhatsApp/Instagram itself.
5. Thursday review shows the whole campus team's current-week progress, blocked work, pending review and open actions. Meeting decisions create owned action items with deadlines. Past weeks remain available.

Use Africa/Lagos for displayed deadlines. Default review/submission time is Thursday 21:00, matching the workbook, configurable by campus. Week keys start Monday. Missing this week's submission must show **Not submitted**, never silently reuse an old good week. Show the date on historical/latest results. Snapshot target, direction, unit and thresholds per reporting period so target edits cannot rewrite history.

## Forms derived from the workbook

- Weekly update: completed work; unfinished work and reason; current work; waiting on whom; blockers; improvement suggestion; next-week focus; support needed. Keep draft fields optional; require actual results and evidence according to the assigned target's policy before submission. Use progressive disclosure for explanation fields.
- Target results: metric, direction, unit, target, actual, evidence and calculated status. Preserve daily/weekly/monthly cadence as explicit configuration: monthly growth must not be mislabeled a weekly outcome, and daily posting needs day-level progress rather than a single ambiguous weekly 1.
- Incidents: date, area, expected/actual outcome, impact, immediate action, cause, corrective action, status and resolution date. Sensitive customer, health, personnel or security details are restricted to author/reviewer; team-wide status is a safe summary.
- Team log: meeting type/date, decisions, actions, owner/deadline; approved changes, reason, approver and effective date. Preserve actor/time/change history.

## Calculation rules

The workbook has 20 example metrics. They become editable templates, not imported live production achievements or irreversible default requirements. Do not infer targets from its sample change-log entries over the actual assigned-target fields.

- Higher is better: attainment is actual / target for positive targets. The workbook's status thresholds are at least 90% of target for On track, at least 80% for Watch, otherwise Below target. Keep those defaults visible and editable; distinguish **target met** from **on track**. Missing values are Not reported.
- Lower is better: actual at or below target is On track. Watch tolerance is explicitly configured in the metric's units. The workbook's generic target + 1 is unsuitable for every metric: adding 1 to a fractional rate would mean 100 percentage points. Use percentage-point tolerances for rates and count/time tolerances for those units.
- Zero targets never divide by zero. A zero-defect target can use count thresholds; display attainment as not applicable where a ratio is misleading. Treat an entered zero as a real result, not an empty value.
- Validate nonnegative counts/durations, valid rate ranges and evidence URL/file metadata. Record corrections and preserve submitted/reviewed history. One result per member, metric and reporting period, with optimistic revision checks to prevent concurrent overwrites.

## Intentional UI

**My week:** clear deadline and next action at the top, followed by a short checklist with actual/target progress, evidence thumbnails or linked proof, blocked-state callouts and a prominent Submit for review action. Edit one task in a focused panel instead of opening a spreadsheet-width form. Show saving, saved, offline/retry and validation states without losing entered work.

**Team overview:** period switcher, plain progress summary and a compact member-by-responsibility list. Expand a member to see their agreed targets and approved work. Separate Not submitted, Awaiting review, Changes requested and Approved. Use text/icons as well as colour. On mobile turn wide metric rows into readable stacked details, retaining the same hierarchy; no horizontal spreadsheet scrolling as the main interaction.

**Thursday review:** desktop split view with submission/evidence on one side and reviewer comments/actions on the other; mobile uses a full-screen review panel with a persistent Approve / Request changes action area. The content calendar shows next-week coverage, intended publishing dates and missing assets. Meeting notes link directly to the action they created.

Use the existing brand typography, spacing, components and accessible focus/keyboard behaviours. Images/evidence use the existing authenticated Cloudinary upload integration. Store links and metadata, not base64 image bodies in task rows. Private evidence requires appropriate private/authenticated delivery; a normal public Cloudinary URL is not access control. External Drive links remain external links; no new Drive integration is required for version one.

## Reminders and reports

Use the existing Celery tick and durable notification/email outbox. No extra worker, scheduler, per-person cron or constant frontend polling. Capture bounded due batches with a uniqueness key of member + assignment/period + reminder kind + due revision. Re-check active membership, campus and outstanding work before dispatch. Completing/submitting cancels outstanding reminders. Deadline edits supersede old intents. Unknown provider outcomes follow the existing no-blind-retry policy; outages recover within a bounded window rather than sending a backlog burst.

Suggested editable defaults: Monday 09:00 kickoff, Wednesday 15:00 progress reminder, Thursday 15:00 due-today reminder and one final reminder an hour before the configured deadline, only when work is outstanding. Meeting reminders follow the actual configured meeting time. Team working days are configured separately from restaurant ordering/delivery days. Notifications deep-link to the relevant week/task. Push needs consent/subscription; permitted email fallback is available when push cannot deliver. A send attempt is not proof of device receipt.

Team daily digest: configurable time, enabled days and channel; a concise campus/team progress summary plus the recipient's own due work. Optional weekly personal/team recap and monthly aggregate use the same snapshots. Avoid one email per edited field or per target. Default scope is counts: new student accounts, agreed qualifying delivered-order counts if enabled, submitted/approved work, blockers and next deadlines. No revenue, profit, margins, delivery cushion, wallet balances, HP conversion rates, private contacts or individual customer orders. Build a server-side allowlisted report DTO; do not forward the internal admin report and try to hide some fields in the frontend.

Existing operational emails currently use explicit private campus recipient settings; being an admin does **not** automatically subscribe every admin. Add a configurable audience choice for that report: designated inboxes or all active authorized campus admins. Re-check role and campus at dispatch; super-admin cross-campus delivery is explicit. Keep the confidential admin report and safe team digest as separate renderers and access policies.

## Small additive implementation batches

1. Campus memberships and permissions; target templates/assignments; period snapshots and audited own-result APIs. Add focused team modules and small navigation/role-capability registry changes. Preserve shared checkout/fulfilment work.
2. My week, team overview and review UI; work/evidence items, weekly narrative, incidents and meeting actions. Retain drafts across errors, paginate history and use existing request deduplication.
3. Existing-outbox reminders, safe team digest and admin-audience configuration. All copy goes in messages.py; reuse current email and push providers. Campus switches and role removal invalidate reads and pending dispatch eligibility.
4. Verify ownership/campus/role boundaries, concurrent drafts/submissions, stale updates, changing targets/deadlines, zero/blank/formula thresholds, report redaction, removed membership, duplicate ticks and interrupted delivery. Test mobile/desktop layouts, keyboard navigation and retry without draft loss. One consenting test recipient only for provider acceptance; no customer-wide tests or database cleanup.

Candidate data modules: team_memberships, team_target_assignments (versioned), team_weekly_reports, team_metric_results (snapshots), team_work_items, team_incidents, team_meetings and immutable audit entries. Reuse existing durable outbox and upload metadata. Unique keys and transactional server-side submission/review enforce workflow; table names alone are not the security design. Inspect current live schema before migration, use RLS/backend-only mutation permissions and preserve current customer roles, accounts and data.

## Acceptance

A designer can see an understandable target, save work, attach proof, get one due reminder, submit, receive revision feedback and resubmit. Their campus admin reviews it; teammates see safe current-week progress; another campus and an unrelated customer cannot access it. A target change affects future work without rewriting old results. The daily team report contains only approved safe counts. Existing customer signup, ordering, wallet and commerce roles continue working.
