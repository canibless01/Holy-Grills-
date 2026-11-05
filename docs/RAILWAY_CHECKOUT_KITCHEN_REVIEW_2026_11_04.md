# Railway and launch flow review — 4 November 2026

## Production verification (read-only)

- Pulled main through `56ecb43` before changing code. Prior unfinished OneSignal edits are preserved in a local stash and were not applied over the owner's completed email work.
- Railway API `/api/health`: HTTP 200; Redis, Supabase and Supabase Auth connected.
- Production audit records show successful scheduled-order, newsletter, blast, abandoned-cart, post-delivery, birthday, win-back, order-lock, HP decay, 120-day HP and tier-grace jobs on 4 November. The scheduled-order scan ran every five minutes; newsletters and blasts had no queued messages in the sampled runs.
- No execution audit records were found for the weekly/monthly rollover tasks. Their schedules are registered in code; production execution of those particular jobs is not yet proved. They were not manually replayed against customer balances or leaderboards.
- Production batch RPC supports the restricted kitchen role. No rider assignment, notification send, test order, account creation, database migration or data repair was performed during this review.

## Changes

- Unpaid payment attempts remain recoverable checkout drafts. They no longer appear in the admin operational order list and dashboard counts, customer history, active-order API or automatic tracking list. Direct recovery/payment URLs remain available.
- Signed-in carts are retained while card payment is pending. Verified payment on return settles the original unchanged cart rows; later additions and edits survive. Duplicate callbacks share one settlement. A paid receipt clears only its own checkout checkpoint. Immediate paid wallet orders retain their existing server-side cart clearing.
- A failed payment launch stays on checkout with recovery available. A closed checkout releases its browser recovery checkpoint so the customer can review their retained cart again.
- Existing abandoned-cart reminders now explain that checkout and payment confirm the order. They remain subject to the existing feature flag and recovery schedule; no new campaign or unconditional push was added.
- Kitchen queue defaults to today's WAT preparation date. A bounded date range supports reviewing earlier unresolved tickets, with historical controls disabled in the UI. Scheduled orders use their scheduled preparation date; normal orders use their creation date. Only paid/partially refunded orders with delivery windows enter preparation.
- Handoff contains today's ready/assigned orders and labels/groups their hostel stops. Admin hostel cards expose missing gate links.
- Scheduled-order notices now use durable order/recipient references. One lookup per campus replaces a query per order. Old scheduled orders are excluded; today's scheduled orders are eligible at the start of their preparation day, without waiting for evening delivery. Structured error results no longer get a misleading cron-success log.
- Weekly streak outcome copy identifies the exact week and missed-day count. Five effective check-in days (including reclaimed days) succeed; four fail. A week skipped entirely cannot reuse an older successful week. Weekly HP amounts still come from the existing reward configuration and pending-cap logic.
- Staff accounts explicitly see that they do not compete in the student leaderboard. Student rankings remain live for the selected period; cron jobs archive completed periods rather than update today's rank.
- Customer menu requests explicitly use the browsing campus and available-only filtering. Quick-add detail and addon reads run in parallel. Admin menu management remains separate.
- Mobile users get a dismissible install banner even when the browser withholds `beforeinstallprompt`; Install opens the native prompt when available or platform instructions otherwise. The browser still controls native installation eligibility.
- Kitchen and handoff polling pause while the document is hidden. Each Celery worker process reuses its Flask application while opening a fresh application context for each task. Default worker concurrency is bounded to two, configurable using `CELERY_WORKER_CONCURRENCY` (a CLI `--concurrency` value takes precedence).

## Operating model and outstanding configuration

- Ordering cutoff is still database-configured; no 16:00 literal was introduced into admission or dispatch.
- Kitchen preparation and rider batches have separate purposes. The kitchen sees paid orders during the ordering window. Rider batches are currently staged when orders become READY, grouped by campus, delivery date, delivery-window ID and gate. The cutoff itself does not create batches or mark food ready. Changing this to create dispatch groups exactly at cutoff would be a separate workflow change; it was not silently introduced.
- On-campus hostels use `hostels.gate_id`; off-campus orders use their selected/nearest gate. Admin → Delivery → Hostels → Edit provides the existing gate selector. Twelve active hostels already have links; FUTACOOPS has no link and needs the operator to choose its correct gate. No geographic guess was saved.
- Rider assignment is restricted to active riders in the batch campus and ready paid orders. A real production handoff was not executed because that would change customer operations. Local role, transaction and handoff tests cover the route contract.
- Keep one beat scheduler. Removing either beat or the worker would stop scheduled work; running duplicate beat schedulers can duplicate enqueueing. No Railway service/resource settings were changed because this session has no Railway management connection. Actual billing savings require Railway metrics; no percentage saving is claimed.
- Physical-device native PWA installation remains a browser/device check. Local Android emulation verifies that installation help remains accessible without a native prompt.

## Verification

- Backend: 957 tests passed with local database URLs and provider credentials disabled.
- Frontend: complete production build, prerender and existing request-sharing/PWA checks passed.
- Paid-cart test uses an in-memory API double: unpaid preservation, one-time settlement, edited/new row preservation and checkpoint cleanup.
- TypeScript check passed. The final client build also passed after checkout recovery refinements.
- Android mobile browser emulation: install help appeared without a native prompt and Install opened the instructions; no uncaught browser errors.
- Final dashboard-count adjustment: 13 focused runtime/analytics checks passed after the full backend suite.
