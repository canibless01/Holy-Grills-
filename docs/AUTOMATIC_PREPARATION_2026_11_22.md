# Preparation at ordering cutoff — 22 November 2026

Implemented as an independent **`auto_prepare_closed_windows`** feature flag, initially **false**. This does not depend on or activate physical-store pickup. Enable it for a campus when the kitchen is ready to use the workflow.

When enabled, the existing Celery worker/beat checks once per minute by default. After a window's effective closing time in Africa/Lagos, its paid orders due today move from received/paid to preparing. Staff still mark Ready; delivery continues through rider assignment/dispatch/delivery, while pickup ends with confirmed collection. Preparation does not award completion HP or pretend that food has been collected/delivered.

- Reuses the ordering gate's precedence: dated windows, campus/global date override, recurring windows, then operating-hours/config fallback. An override extending the cutoff prevents early preparation. Failed override reads stop automatic actions.
- Unpaid, future-day, old-day, test and still-open-window orders are excluded. A manually closed/all-day closed window and unsupported overnight windows stay manual. An order tied to a window absent from today's effective schedule is not guessed into another window.
- Uses normal status validation, payment/due-day checks and compare-and-set transitions. A competing kitchen action, cancellation or worker scan cannot apply the transition twice. Failed transitions remain eligible for a later scan.
- Processes at most 200 eligible orders per campus per scan; remaining orders follow on subsequent scans. Timing is approximately one minute plus queue/network delay, not a guaranteed instantaneous timer.
- A dedicated background-only service-client path is required because an ordinary request client has no worker JWT. HTTP requests and calls impersonating a staff actor are rejected from this private path. Browser/client financial and role checks remain unchanged.
- Uses the existing deployment's Celery worker, beat and cron lock. **No external cron provider was added.** Admin System displays its cadence/receipts and retains the existing protected manual-run controls. `CELERY_AUTO_PREPARE_SCAN_MINUTES` optionally changes cadence; no environment edit is needed for the one-minute default. Existing scheduled-order reminder cadence is unchanged.

## Verification

- Seven targeted tests cover cutoff/WAT/closed-day exclusions, strict failed reads, disabled admission, paid/day/window/campus query restrictions, retry/conflict behavior, denied HTTP background access, lock release and beat registration.
- `tests/automatic_preparation_sessions.py` ran the actual producer and status service against disposable PostgreSQL inside a rollback: paid delivery, pickup and today's scheduled order prepared; unpaid, future, current-window, yesterday and test orders stayed received; repeat scan changed zero; no ready/dispatch/HP was generated. The older disposable clone's missing `is_test` column was reproduced within that transaction from the verified live column definition, then rolled back. No provider transport ran.
- Combined backend **1,974 passed**, including the latest other chat's editor/reporting changes and both new features. Frontend typecheck/build and the native pickup controls passed; see [pickup evidence](STORE_PICKUP_2026_11_22.md).
- Test Two migration `20261122154512_auto_prepare_closed_windows_disabled.sql` applied once. Exactly one global row each for auto preparation and pickup, both false; no new table or SQL helper/overload for automatic preparation.

## Operational acceptance

Observed the deployed job’s first successful receipt at **16:50 WAT on 22 November**, revision `34a5c97`, with an empty result while the release flag remained off. Vercel frontend and Railway API, worker and beat all reported successful deployment for that application revision. Before enabling for actual orders, configure/review the campus ordering cutoffs. The real enabled production cutoff/customer notification observation remains distinct from the passing local producer/database proof. No live customer order or feature flag was changed to manufacture that observation.
