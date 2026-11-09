# Organizer workspace — 8 November 2026

This completes the initial organizer draft → admin review/publication → own-event statistics/attendance → requested settlement → admin-recorded bank-transfer workflow. It supersedes the interrupted-work checkpoint for implementation status. It is not a claim that every ticketing-platform enhancement or real device/provider has been accepted.

## How to use it

1. A normal account signs up with its campus. In Admin → Users, its campus admin or a super admin assigns **Event Organizer**. The account refreshes/signs in to pick up the role.
2. The organizer opens **/event-manager**, also available through the student/staff panel switcher. Admins can enter through the admin header or Events → **Organizer / settlement** on the relevant event. Each organizer sees only owned events; admins retain campus scope and super admins retain global access.
3. The organizer creates an event draft (title, description, venue, WAT times, capacity and optional Cloudinary image), saves it, and submits it. Submitted/approved drafts are not directly editable by the organizer. An admin can request changes with private feedback; the organizer edits and resubmits.
4. Admin event/tier controls finalize public prices and attendee HP. The workspace assigns the organizer and sets the **separate fixed organizer amount per tier**. Approval requires active tiers to have agreed amounts, then publishes the event. Set ownership/terms before tickets are issued; ownership cannot be changed after issuance. Super-admin draft creation supports both the selected campus and global scope.
5. The workspace shows confirmed/pending/cancelled tickets, check-ins, agreed amounts, earned/paid/reserved/available settlement balances and attendee search/export. It offers a locally rendered/downloadable venue QR and ticket scanner/manual fallback. Admission uses the existing atomic reward receipt, so retrying a checked-in ticket cannot award HP again.
6. After an approved event ends, its organizer requests the available amount with bank details. The admin approves/rejects the request, then records the reference only **after completing the bank transfer**. The application does not send that transfer. This balance is separate from the shopping wallet.

Example: public cash price NGN1,600; agreed organizer amount NGN1,500. A confirmed paid ticket accrues NGN1,500 to the organizer. The admin additionally sees recorded cash and cash less organizer earnings before provider fees. Current prices are not multiplied to invent sales revenue.

## Financial and privacy rules

- The agreed amount is captured at ticket reservation. Later tier changes do not rewrite existing ticket entitlements. Unpaid holds and cancelled/refunded tickets do not add available earnings.
- Requests reserve the server-computed available amount under the event lock. Browser-supplied amounts cannot choose the payout. Retries reuse the same request; cancellation, approval and recorded transfer have safe replay behavior.
- Refunds share the event lock and reduce available earnings. Approval/recording rechecks the balance. A later refund after a recorded payment exposes an adjustment due rather than concealing an overpayment.
- Contracts, immutable ticket earnings, payout/bank records and review feedback are in the private hg_internal schema with RLS and service-only grants. Public catalogue/customer ticket rows contain no organizer financial agreement or private feedback fields.
- Privileged RPCs revalidate active actor/ownership/campus and have one intended signature, no browser EXECUTE. Existing protected admin/balance role rules remain; a campus admin may appoint/manage its subordinate organizer role.
- No extra credentials or automatic-bank-transfer provider is introduced. Organizer artwork uploads use the existing Cloudinary integration, signed into the organizer's own folder.
- Review/payout notices target the organizer or relevant own-campus/super-admin staff and link directly to the event workspace. Request/version-based IDs suppress duplicates. Notice capture now commits inside the business transaction; Python only wakes the existing durable dispatch. See EVENT_RELIABILITY_2026_11_09.md.

## Verification

- Native Chromium at **393px and 1280px** passed draft creation with a lost committed response and stable request UUID; submission/locking; private change requests, draft editing with immediate detail refresh and resubmission; admin organizer terms/publication; recorded earnings; decoded/downloadable venue QR; attendee search; admission response-loss replay; formula-safe CSV; payout request response-loss replay; approval/recorded transfer; wrong role/owner denial; actual student-page/panel return navigation and no horizontal overflow. Controlled HTTP endpoints were used, not production customer writes.
- Real handler/middleware tests cover role/deactivation/campus gates, draft field smuggling/validation/WAT conversion, server-bound actors/amounts, review validation, ticket QR scope, export limits, central errors, scoped Cloudinary folders, direct-event notice links and approved venue QR.
- The fresh **tests/sql/event_organizer_settlement_loop.sql** passed through Supabase with BEGIN/ROLLBACK fixtures. It covers actual role appointment, global/scoped super-admin drafts, submission/private feedback/resubmission, review/terms, snapshot immutability, pending exclusion, own admission/replay, cancellation/request/approval/payment receipts, refund balance checks, overpayment visibility and private schema/RPC access. All fixtures rolled back; no genuine account/event, real provider message or money movement was used.
- The pre-existing atomic admission and paid-refund SQL suites also passed after the accounting conversion. Security advisor counts remain at the five pre-existing categories/39 findings; no new finding was introduced. Intentional policyless service tables, pg_net placement, public/RLS helper notices and leaked-password protection remain separately tracked. See the Supabase [advisor remediation index](https://supabase.com/docs/guides/database/database-linter).
- Frontend TypeScript, targeted ESLint, central-message/route checks and the complete client/SSR/seven-route prerender build pass. **1,350 backend tests passed** after integrating main’s automatic-funding changes.

## Migrations

The five initial organizer migrations, through 20261108095008_private_event_organizer_accounting, are already on main with the exact applied history. This completion adds:

- 20261108100934_replay_cancelled_event_payout_requests
- 20261108101107_private_organizer_review_feedback
- 20261108102258_super_admin_organizer_draft_scope

Each was applied once, with intended grants and no duplicate helper overload/snapshot trigger. Intermediate public financial/feedback columns are removed by the later privacy migrations; no unused duplicate public contract fields remain.

## Still separate

Event-wide cancellation/rescheduling with durable attendee notices and an explicit refund policy; exceptional ticket receipt/resend/recovery cases; configurable check-in opening times; independent simultaneous-session/process-kill proofs; actual handset camera and real bank-transfer/provider acceptance. Group purchases, transferable tickets and delegated door staff are additional product scope, not silently included in this release. The wider admin/database audit remains open in GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md.

## Admin event layout — 9 November 2026

Admin → Events now separates event details, venue/date, attendance/HP, ticketing controls, workspace navigation and publication/deletion. Mobile cards use a three-column tool grid; wider screens use six columns. The shared admin header puts its controls on a separate row below the wide-desktop breakpoint, preserving the page title. New display copy is registered in `messages.py`; event API handlers and settlement rules are unchanged.

Verification: native Chromium at 360, 393, 768, 1280, 1440, 1536 and 1920px with a long title/venue, no horizontal overflow, readable header and touch-sized event tools. Controlled API interaction runs at 393/1280px also covered paging, publication, WAT editing, funding selection, venue QR display/download, panel retries, attendee search, check-in response-loss replay, CSV formula protection, ticket-tier switching and sales cash reporting. These checks use synthetic API responses and make no production writes.

TypeScript, targeted ESLint, central-message resolution, and the complete frontend production build/client+SSR/prerender passed. Existing unrelated fallback-copy drift remains reported by the message checker.
