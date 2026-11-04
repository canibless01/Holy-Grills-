# Whole-site status and hosting costs — 4 November 2026

All operating dates/times use Africa/Lagos. This report supersedes older “remaining” lists where they conflict. “Implemented” and “verified live” are different: no new real customer, payment, notification blast or production test order was created in this pass.

## Google reviews

The owner supplied `https://g.page/r/CT3sD6yYtneQECA/review`. It is configured in the production site's Vercel project as `VITE_GOOGLE_REVIEW_URL` for production, preview and development. The delivered-order review prompt now accepts this direct Business Profile link, with the older optional `VITE_GOOGLE_BUSINESS_PLACE_ID` retained as fallback. A Place ID is an identifier, not an API key. Neither Places API nor Google Cloud billing is needed to open this link. Google Maps/Places search configuration and its billing requirements remain separate.

Customers choose whether to leave a Google review. The link is available regardless of their in-app rating; an in-app review is not automatically published to Google. The app does not award a reward specifically for posting a Google review. Link validation and fallback behavior have automated coverage. Google controls sign-in, review publication and moderation.

## Whole-site coverage

| Area | Evidence/status | Outstanding confirmation |
|---|---|---|
| Home, story, campus navigation, SEO | Public catalogue/browser checks and build/prerender checks passed previously; brand description belongs in metadata/structured data, unwanted hero paragraph removed. | Search Console ownership/submission and indexing observation; search rank/autocomplete cannot be guaranteed. |
| Menu, item details, modifiers, cart | Campus availability/price/stock checks; bulk cart availability; scoped short metadata cache; browser menu round trip previously passed. | Sustained real-device speed measurements across different connections. |
| Signup/login, profile, roles | Autoconfirm-issued sessions persist and navigate home; owner grants checked through authenticated API; super-admin role applied. | Hosted password-reset round trip and installation of the prepared branded Auth templates. |
| Welcome HP, free sides, tiers, referrals, rewards | Corrected actual-grant welcome copy and idempotent signup recovery; prior owner API reads showed 50 active HP and one side. Referral/delivery/unlock/replay regression coverage exists. | No fresh real-customer referral/delivery reward cycle claimed. |
| Wallet and payments | Wallet debit/payment replay and unpaid isolation tested, including rolled-back database flows. | One controlled real Paystack payment and return/webhook observation; no real charge was performed here. |
| Checkout, delivery addresses, reservation dates | Database-backed cutoff and calendar; map rendering/CSP and emulated GPS previously passed. Unpaid cart retained; paid confirmation/counter rules corrected. | Physical-phone GPS permissions/accuracy and Maps billing/account continuity. |
| Ordering calendar, Sunday and prelaunch | FUTA intake 00:00–16:00 Mon–Sat, delivery 19:30–20:30; Sunday closed. Nov 4–8 dated closures route preorders to Monday Nov 9, subject to capacity. Sunday-specific message and calendar checks passed. | Observe first real Monday service; dates/capacity remain editable database configuration. |
| Order history, guest email tracking, inbox | Guest inbox link confirmed working by owner; unpaid records excluded from operational lists; notification routes and ownership regression coverage. | Physical push tap into signed-in/guest order; no new outbound blast in this pass. |
| Kitchen queue, preparation summaries, rider batches | Date-based queue and paid-only preparation; actual DB rollback exercised paid orders through ready, same gate/window/date grouping, kitchen rider assignment, pickup, delivery and completion; wrong rider denied. | First real rider handoff. Kitchen groups preparation by service day; rider batches group destinations and become usable when food is ready. |
| Leaderboards, weekly streaks, monthly prizes, Hall of Fame | Staff excluded; exact missed-day wording; campus/period isolation; transactional monthly grants and replay tests; scoped ranking fixes. | First ordinary weekly run Nov 9 and monthly archive Dec 1; historical user rewards were not replayed. |
| Events/tickets/check-in, catering | Current route wiring and regression suite included. | No new real guest ticket payment/email/check-in or catering booking performed in this pass. |
| Marketplace, squads, order locks, challenges | Current route wiring and regression suite included. | No new full multi-user browser transaction in this pass. |
| Ambassadors, sharing, community/newsletter | Prior mobile/share fixes and build regression checks; current routes included. | Physical WhatsApp share confirmation and new real campaign delivery not repeated here. |
| Admin settings, campus/delivery/menu management, analytics | Current wiring checked; existing validation/role regression suite included. | Not every admin form has a fresh interactive browser audit. |
| Email, push, recovery, scheduled campaigns | Owner reports OneSignal email/push resolved; existing provider routing preserved. No provider or SMTP migration added here. | Actual provider receipt/delivery and physical-device appearance require an authorized outbound test or normal traffic. |
| PWA/mobile install | Production non-private Android Chromium reported no manifest/installability errors and active service worker; Android/iPhone/iPad install help checked. | Actual handset installation; browsers control native prompts and can suppress them. |
| Scheduler/worker/monitoring | All 18 jobs retained; scan cadence reduced; cron monitor batches reads; background app now omits web routes/Swagger. | Confirm all Railway services on pushed revision, one beat instance, and explicit worker concurrency overrides. |

Detailed previous evidence: [ordering and rollover](PRELAUNCH_COMPLETION_AND_CHECKLIST_2026_11_04.md), [Sunday and mobile PWA](SUNDAY_NOTICE_AND_MOBILE_PWA_2026_11_04.md), [signup, rewards, GPS](SIGNUP_PAYMENT_GPS_RESULTS_2026_10_30.md), [settings versus environment](SETTINGS_AND_ENVIRONMENT_MAP_2026_10_30.md), [Auth templates](SUPABASE_AUTH_EMAIL_TEMPLATES.md).

## Current static wiring audit

Regenerated from the current normal Flask app, rather than relying on the October route reports: 503 frontend API call sites and 459 registered API rules. Three initial unmatched expressions are query-string/template parsing artifacts: delivery-window status calendar query, rider handoff assignment campus query, and batch advancement campus query. Their real routes exist. No confirmed missing frontend-called route was found in that comparison.

The scanner also flags 49 potential write-field mismatches. These are heuristic review leads, not 49 broken forms: it includes database-read fields (event publication), server-written fields (newsletter unsubscription timestamp), and payloads passed through variables. Zero flagged field names are absent from the entire frontend source. This is not proof that every payload contract is correct; exhaustive form-by-form browser verification remains outstanding. Nineteen routes lack a recognized direct frontend caller, including internal tracking/support routes and parser artifacts; that alone does not establish a defect.

## Railway screenshot analysis

| Service | Displayed cost |
|---|---:|
| Celery worker | $0.1787 |
| API | $0.0670 |
| Celery beat | $0.0485 |
| Redis | $0.0116 |
| Total | $0.3058 |

RAM accounts for $0.2909, about **95.1%** of this displayed total. The worker accounts for about **58.4%** of total cost. CPU is a small share. The 743.24 GB etc. usage figures are accumulated usage, not an assertion of instantaneous allocated memory. The screenshot does not expose enough period/unit information to forecast a monthly bill.

Previously reduced frequent scans from 768 to 336 invocations/day (56.25%); that reduces database/CPU work, while always-running processes still consume memory. No scheduled business job was removed. Existing configuration defaults worker concurrency to one; an explicit Railway command override wins.

This change moves HTTP-only imports into the HTTP app factory. Scheduler and worker Flask contexts retain configuration and production-secret validation without loading every API blueprint, CORS and Swagger. Each task still receives a fresh Flask application context, with no cross-task `g` state.

Controlled local subprocess startup measurements, before/after:

| Process | Before peak RSS | After peak RSS | Reduction |
|---|---:|---:|---:|
| Scheduler module load | 44.39 MiB | 35.91 MiB | 19.1% |
| Initialized worker context | 47.64 MiB | 36.04 MiB | 24.3% |

These are local startup measurements, not observed Railway billing savings. Tasks can load additional modules while running. No service was resized or removed, and no Railway management/billing connection is available in this session. Compare Railway's daily memory graphs after rollout; accumulated historical usage will not disappear. Keep one beat and a concurrency-one worker unless measured queue demand justifies more processes. Avoid disabling the worker/beat because payment, campaign and reward jobs depend on them.

## Verification for this change

974 backend tests passed, including four new background-context/import checks. Frontend TypeScript check and the complete client/SSR/prerender production build passed, including the new direct Google review-link tests. `git diff --check` passed. No production test data is retained by these code checks.
