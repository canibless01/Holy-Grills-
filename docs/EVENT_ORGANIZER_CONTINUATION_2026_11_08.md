> Implementation status superseded by [organizer workspace completion](EVENT_ORGANIZER_WORKSPACE_2026_11_08.md). The text below preserves the environment-interruption checkpoint.

# Organizer workspace continuation — 8 November 2026

## Owner-approved behavior

Only approved event_organizer accounts receive an organizer workspace. Campus admins/super admins appoint that subordinate role and review events. Organizers create drafts and submit them; admins finalize public prices, HP pricing, attendee HP awards and a separate fixed organizer amount for every active tier before publication.

Example: a customer pays NGN1,600; the agreed organizer amount is NGN1,500. The organizer accrues NGN1,500 for a valid paid ticket, regardless of the public price. This balance is separate from the shopping wallet. Organizer requests and admin approval/recording of an already-completed bank transfer are implemented at the database level; no automatic bank transfer or wallet credit is performed.

## Published preceding work

- eb6f62c: browser maintenance grants removed, webhook payloads writable only by backend service, scoped log reads retained.
- f5c9294: shared atomic webhook replay claims; scoped/stale reads, WAT dates, paging and error Retry; 1,268 backend tests.
- bf559bf + 23ba19a: native event paging/publication, WAT/funding inputs, local downloadable QR, attendee search/admission, tier sales controls, recorded-cash metrics, CSV defense and protected issued-event/tier history. After correcting the message registration, the production client/SSR/seven-route build passed. Backend 1,277 passed; mobile/desktop native event and existing refund forms passed.
- Inactive-account access to two historical report RPCs was closed and checked with fresh rollback fixtures.

Other-chat commits on main are preserved. The latest checkpoint is not whole-event or whole-database sign-off.

## Applied organizer migrations

The five files in this commit were recovered verbatim from the actual Supabase migration statements, not reconstructed from an invented timestamp:

1. 20261107203500_add_event_organizer_role
2. 20261107203834_event_organizer_workspace_and_settlements
3. 20261107204119_event_organizer_attendee_directory
4. 20261107204202_event_organizer_statistics
5. 20261108095008_private_event_organizer_accounting

Do not reapply these as new migrations. No genuine account was appointed and no customer payment/payout was executed.

The final schema retains events.organizer_id and adds review state. Private financial storage is hg_internal.event_organizer_terms (one agreed amount per tier), event_ticket_earnings (immutable amount captured when the ticket is reserved) and event_payout_requests (request/approval/manual-transfer receipts). The intermediate public financial columns introduced by migration 2 are removed by migration 5; public catalogue/customer-ticket reads do not expose organizer agreements.

All privileged workspace/accounting/directory RPCs are service-only and revalidate active actor, ownership or admin campus. Organizer drafts have read-only browser policies, not direct write/publication privileges. Role changes retain the existing protected admin/balance restrictions. The event admission helper accepts an active organizer only for their own event.

## Executed database proof

Fresh BEGIN/ROLLBACK fixtures passed draft/submission/admin review, owner isolation, fixed earnings, unpaid exclusion, changed terms retaining old ticket amounts, own-event check-in/replay, payout request replay/reservation, admin-only approval, required transfer reference, refund recheck and visible overpayment after a later refund.

After the private-accounting conversion, a second rollback loop passed private terms/immutable earnings, own attendee search/statistics, payout/receipt replay/refund accounting, absent public financial columns and denied browser financial access. Existing event_admission_atomic_rollback.sql and paid_event_refunds_rollback.sql were fetched from current main and passed again through Supabase. No provider message or real money movement was used by these SQL fixtures.

## Local application work — NOT published or accepted yet

At /workspace/Holy-Grills- there are pending additions:
- Backend app/routes/event_organizers.py: draft/list/edit/submit, review/configure, account statistics, attendee search/export/check-in and payout request/review endpoints.
- Blueprint registration, central backend messages, role validation/account controls, organizer-owned Cloudinary upload folder and notification categories.
- Frontend src/pages/EventManager.tsx and src/lib/eventOrganizerApi.ts; user role type and admin role-picker additions.

These files have NOT passed static/browser/regression verification. Do not present the portal as available to organizers yet.

The attempted route/navigation/message wiring command did NOT execute because the execution environment became unavailable. Still wire App.tsx /event-manager, Login role home, PanelSwitcher, admin event/header links, frontend central FE_ORG message keys, then regenerate Vercel route configuration. Review existing notification action-URL handling for the new route.

Local tests/sql/event_organizer_settlement_loop.sql still references the intermediate PUBLIC snapshot columns; update it to the final private terms/earnings before rerunning. Do not run that stale file unchanged.

The private accounting SQL draft remains /workspace/work/private_event_organizer_accounting.sql; live migration 20261108095008 is authoritative. Attendee/statistics SQL drafts are also in /workspace/work. The migration files in this GitHub commit now close the history-recording gap even though the shell environment is down.

## Required finish sequence

1. Restore/reattach the execution environment. Preserve pending files, fetch latest main and integrate without force pushing. Some untracked local migration files now correspond to tracked files on main; reconcile equal contents rather than creating duplicates.
2. Finish route/navigation/message wiring and inspect frontend state/mutation locks and role gates. Fix any remaining backend validation, response-loss and lifecycle gaps.
3. Add real-handler authorization/validation/notification/upload-folder tests. Extend fresh rollback tests for direct role appointment, deactivation, private-data grants, owner isolation and payout concurrency/replay. Verify one intended signature/policy/trigger and no unused public financial fields.
4. Run native organizer plus admin journeys at mobile/desktop sizes: create/save/retry/submit, request changes/edit/resubmit/approval, price/HP/organizer terms, attendee search/export/check-in/QR fallback, payout request/retry/approval/recorded receipt/refund change, wrong role/owner/campus and reload.
5. Run TypeScript, ESLint, central-message/route checks, full frontend build, appropriate backend regressions and security advisors. Fetch/rebase and push progressively.
6. No actual bank payment or broad broadcast during audit. Preserve real users/content.

Payout request eligibility currently opens after the approved event ends. Unknown/failed manual-transfer confirmation must be resolved by inspecting the recorded request, not by sending another bank transfer. Review repeated cancel-state handling before acceptance. Organizer notices currently depend on post-transaction backend dispatch; complete crash-window recovery is not proved by these database tests.

## Other full-event gaps

Event-wide cancellation/rescheduling with durable attendee notices and selected refund policy; receipt/resend/recovery exceptions; configurable check-in opening windows; independent simultaneous-session/crash proofs; real-device camera and bank receipt acceptance. Group/multi-ticket purchases, delegated door staff and other ticketing-platform enhancements require explicit product scope, rather than being silently certified.
