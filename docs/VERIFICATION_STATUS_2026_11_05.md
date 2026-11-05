# Launch verification — 5 November 2026

This is the current status; earlier dated reports retain their historical observations. No live customer payment was charged/refunded, no broadcast was sent and no audit fixture was retained.

## Verified

- All four `92308cb` deployment checks succeeded: Railway API, worker, beat and Vercel. API health reports that revision with database, Auth and Redis connected.
- At **13:00 WAT**, the production worker completed scheduled orders, scheduled blasts, newsletters, cart recovery and post-delivery recovery on that revision. The new notification recovery result was `due: 0, checked: 0`, with a successful job receipt. An empty scan verifies deployment/execution, not an actual interrupted delivery.
- **33 production-database rollback scripts passed.** [Machine-readable list](evidence/launch_verification_sql_2026_11_05.json). Covered configured ordering/capacity/day/batch boundaries, kitchen/rider handoff, stock, ordinary/physical rewards, attempted/unclaimed delivery, supported promo/campaign/ambassador/refund conservation, earned promises, event admission, active milestones, check-in/weekly recovery, monthly rollover and notification leases/review/privacy. This is the enumerated matrix, not proof of every theoretical combination.
- Backend regression suite after the event fixes: **1,120 passed**. Previous full frontend build and mobile/desktop notification recovery forms passed; this continuation changes no frontend component.
- Supabase SMTP reset email arrived and its reset-page link worked, as explicitly confirmed by the owner. OneSignal push/email and guest inbox tracking receipt were also previously confirmed by the owner.

## Event financial fixes found by verification

Applied `20261105120840_restore_expired_event_reservations.sql`:

- Expired pending tickets now return exactly the wallet funds and HP reserved, release their recorded promo use and tier seat, and save a receipt atomically. Unpaid card amounts are never credited. Paid tickets cannot expire through this path. Replay cannot return funds or release a seat twice.
- New registration releases stale holds for that event before capacity checks, instead of waiting for the next cron sweep. HP spend references use the ticket ID, allowing rebooking after an expired reservation without colliding with the old spend.
- Guest identity comparison explicitly normalizes email case/spacing. The prior `citext` equality ran inside a search path without the extension's operators, allowing case-only duplicate guest reservations. Guest promo limits now apply per normalized email across events; promos from another campus are rejected for guests and account holders.
- The existing cron owner has no JWT. Its temporary service claim is scoped/restored around the protected ledger helpers. A real no-JWT rollback test passes. The expiry cron remains every 15 minutes, with a bounded 200-ticket scan; no new scheduler/service is added.
- Payment confirmation now respects a false QR-email return value instead of reporting `email_sent: true`. A repeated paid webhook still does not blindly resend.

The native new matrix exercised HP/wallet/card splits with a promo, interruption and response replay, rebooking, amount mismatch, duplicate payment callback, unpaid/paid admission, guest duplicate/expiry/coupon limits, free registration, campus/balance denials and cron context. The security advisor retains its five existing categories/39 findings; no new finding appeared. At inspection there were zero event tickets and zero historic expired reservations with account debits, so no customer balance backfill was performed.

## Still requires proof or implementation

| Boundary | Exact remaining item |
|---|---|
| Real payment | One completed owner-controlled card journey through the intended Railway payment mode, return, tracking and corresponding provider webhook receipt. SQL payment fixtures and mocked providers do not substitute for this. |
| Real devices | Actual Android/iPhone installation, handset GPS permissions/saved-address selection and notification-tap destination. Emulated browser checks do not operate the owner's phone. |
| Infrastructure | Railway's actual replica count/start-command settings require management access; deployment checks and single recent receipts do not prove a single beat replica. The ordinary next weekly/monthly run still needs observation on its scheduled date. |
| Paid event refunds | No public/admin paid-ticket refund workflow was found. Expired **unpaid reservation** return is now verified, but paid-ticket cancellation/refund and reversal of already-earned admission HP are not implemented or certified by this fix. A card capture arriving after expiry remains rejected for admission and requires a payment-support refund; this change does not initiate provider refunds. |
| Guest email durability | Event-ticket registration/payment-to-email capture is now atomic for guests and members; see [ticket email recovery](EVENT_TICKET_EMAIL_RECOVERY_2026_11_05.md). Other direct guest order/catering email utility calls and unrelated business-action-to-notification creation still need their own boundary proof. |
| Remaining reward exceptions | Tier/non-active milestone boundaries and the remaining exceptional special/menu-linked reward variants need their own recovery evidence. Completed specific matrices above remain valid. |
| General admin audit | Native user/staff/settings/webhook and other pages still have open groups in [general site audit](GENERAL_SITE_AUDIT_PROGRESS_2026_11_04.md). Concurrent admin-chat review/report fixes are integrated. |
| Brand acceptance | Hosted Auth email template appearance and Search Console owner actions remain separate from working SMTP and implemented site metadata. |

Independent simultaneous database sessions and a deliberately killed production process were not exercised. Row-lock exclusion, lease expiry, atomic rollback and idempotent replay were verified with controlled transitions. These remaining entries are not silently marked complete.

The legacy first-order hot-dog gift is currently disabled and its configured launch window has expired. It is outside the currently enabled launch path; re-enabling it requires a separate recovery audit.
