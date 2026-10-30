# Community workspace, batch pickup and launch checkpoint — 28 October 2026

## Workspace and permissions

The existing role is community_manager (the campus/community ambassador manager). Added /community-manager using the existing admin shell and the same three ambassador components: Campus Ambassadors, Promo Distribution and Monthly Reviews. Admin and super-admin can open it from their header and retain the superset of those permissions. It is not a new privileged role or a duplicate implementation. Community managers see only their three sections; kitchen/rider shortcuts are hidden for that role. Their panel switch now returns to the student site and back. The existing /admin community-manager entry remains compatible. The SPA route configuration is synced.

Controlled Chromium tests cover manager → student → manager, admin/super-admin → workspace → admin, restricted shortcut visibility and admin tagging control. The header search becomes a toggle at intermediate desktop widths so it does not overlap the new navigation controls.

## Batch operations

Admin Delivery opens on Batches, Orders has a direct delivery-batch shortcut, and an unassigned batch explicitly says Assign rider. The existing management modal lists its orders, assigns the entire ready group, reassigns waiting work or splits selected assigned orders. Orders are grouped there by gate/window/delivery date; this is distinct from the individual-order ledger. Automatic staging happens when paid orders become ready, not for all received/future orders.

Kitchen already has window-wide Received → Preparing and Preparing → Ready actions plus dated future preparation preview and ready-group handoff. Future prep-day enforcement and actual physical reward kitchen/rider transitions were verified in the preceding evidence.

Added rider Collect batch · start deliveries. It collects ready/assigned orders through existing per-order ownership/status endpoints, reports successes/refusals and refreshes. It is a bulk UI operation, not one all-or-nothing SQL transaction. A retry targets only work still awaiting pickup. Delivered stays individual. Browser tests execute one success/one conflict, then retry the remaining order, and assert three individual Delivered controls. Fixed rider earnings history to consume the API's batch_id/amount/paid_at/completed_at fields, preserve fractional naira, and distinguish unpriced batches. The actual paid API shape now appears as paid in the browser.

## Hero scope

Moved the existing active FUTA hero (Bring your people, we bring the fire) from campus scope to global by changing its campus_id to NULL. No slide or image was duplicated/deleted, and content/timing remained intact. Actual anonymous-role SELECT confirms the global hero is visible. The unrelated audit-campus hero was preserved because database cleanup is paused. Global CMS edits remain super-admin-only under the existing policy.

## Financial helper boundary

Existing transfer, normal/flash redemption and legacy refund-reservation functions allowed authenticated execution even though their Flask callers already use the service client. Removed PUBLIC/anon/authenticated execution and retained service_role execution through one privilege-only migration. This prevents direct callers bypassing the application entry points and snapshot/eligibility handling. No function signature/table was added. The direct transfer probe did not complete a mutation: existing nested profile protection refused it; its fixtures rolled back. Do not interpret the probe as a demonstrated successful unauthorized transfer.

Real SQL now proves direct authenticated execution is denied for all four helpers; physical reward redemption → checkout → kitchen/rider → refund still passes through the trusted path. Advisors confirm these four helpers are no longer listed as authenticated-executable. Other historic findings remain for separate review. See https://supabase.com/docs/guides/database/database-linter . The CLI limitation and actual timestamp fallback described in the preceding migration evidence still apply.

## HP and email state

Food HP is awarded at delivery, not merely order submission. The existing delivery flow uses admitted food economics, excludes delivery fees, unlocks pending HP and distributes squad shares. Corrected HP-unlocked notification copy to read the actual unlock helper result; it previously inspected the primary award result, which did not contain the unlocked amount. A focused test proves a 30-HP unlock produces the 30-HP notice alongside the earned award. Auxiliary-hook outage recovery is not a completed all-path sign-off.

Supabase Auth sends signup confirmation/resend verification and recovery/password-reset email via its configured Auth SMTP. The app invokes /auth/v1/signup, /auth/v1/resend and /auth/v1/recover. These emails do not pass through send_email_routed. Application order/reward/operational/blast email uses Resend or OneSignal according to routing/preferences.

The app currently discovers exhausted quota from an explicit provider rejection, then attempts the alternate provider once. It does not count to 100/200 locally, and ambiguous timeouts do not switch providers because the first provider may already have accepted the email. Resend-only custom/unsubscribe headers are not discarded to force fallback. Consequently, not every newsletter is cross-provider routable. OneSignal email must be approved/configured before it can accept fallback. Supabase Auth SMTP has no application-router failover; if it shares an exhausted Resend account, authentication email can still be affected. Durable shared quota counters, reserved authentication headroom and durable dispatch/retries remain unfinished. The draft SQL is deliberately not applied without the application integration.

## Validation and remaining work

Backend suite: 708 passed. Frontend typecheck/build and changed-file lint pass. Browser workspace/bulk-pickup/earnings and explicit admin-refund/capacity regression checks pass. The helper-privilege and physical-reward SQL scenarios pass with fixtures rolled back. No real transfer, provider charge/refund, push or customer email was sent by these checks. The global hero scope change was the requested persistent content change.

Remaining launch cases are in LAUNCH_REMAINING_2026_10_28.md: real payment/funding/split/return interruptions and guest provider refunds; wider reward stacking, legacy/menu-linked rewards and delivery exceptions; durable email counters/queue/retries; real push receipt/click and running worker evidence; device map/Chrome install and deployed storefront/session presentation; remaining per-action role/security checks. Events/marketplace and database cleanup remain deferred. This is not a 100% A–Z certification.
