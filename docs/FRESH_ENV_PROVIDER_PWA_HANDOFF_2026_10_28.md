# Fresh environment handoff: provider, deployment and device verification

Latest checkpoint at creation: main 17e4753. Always fetch current main because another chat continues delivery/reward/promo/recovery work. This document supersedes stale provider-blocker wording where the user has already confirmed Cloudinary uploads work.

## Environment changes

Apply these to the new Codex cloud environment's network/allowed-domain configuration. Preserve all existing domains and package-manager presets. Enter bare hostnames if the UI requests domains, not URL paths.

Core application/provider hosts:

- holygrills.online
- www.holygrills.online (only for checking the www/canonical redirect)
- holy-grills-backend.onrender.com
- zaxdkrmzyibkvlsrgmvq.supabase.co
- api.cloudinary.com
- res.cloudinary.com
- api.paystack.co
- checkout.paystack.com
- paystack.com
- js.paystack.co
- api.resend.com
- api.onesignal.com
- onesignal.com
- cdn.onesignal.com

Additional hosts for the already-requested map and native-share/browser checks:

- nominatim.openstreetmap.org
- a.tile.openstreetmap.org
- b.tile.openstreetmap.org
- c.tile.openstreetmap.org
- www.google.com
- maps.google.com
- wa.me
- api.whatsapp.com
- web.whatsapp.com

Keep GitHub access linked; existing github.com/raw.githubusercontent.com/package hosts should stay allowed. No new GitHub token is needed just because this list exists. Payment providers, Google Maps and OneSignal may use further redirect/3DS/subscription-specific hosts; inspect the real request failure and add only the exact required host. This list covers current source hosts, not every possible future provider redirect. Cloudinary image CDN access and browser SDK access must be allowed for browser tools as well as shell requests.

The old environment's enforced policy still contains only Render/Supabase plus preset package hosts. Saving settings for a new environment does not establish that the old running session adopted them. Start the fresh chat with the updated environment attached; verify observed readiness/revision there. Credentials stored only in a personal vault are not necessarily bound into a running backend process.

### Backend/audit runtime variables

Keep the existing Supabase URL, anon and service-role key bindings, DB connection if used, SECRET_KEY and JWT_SECRET. Do not replace existing production signing keys. Bind the following using the vault/secret fields, not source-code fallback values:

| Variable | Where/use |
| --- | --- |
| CLOUDINARY_CLOUD_NAME | Audit backend and Render backend; account's actual cloud name |
| CLOUDINARY_API_KEY | Audit backend and Render backend |
| CLOUDINARY_API_SECRET | Audit backend and Render backend; server only |
| PAYSTACK_SECRET_KEY | TEST secret in the audit backend for sandbox checks; never silently replace production with a test secret |
| PAYSTACK_PUBLIC_KEY | Matching test public key if the deployment uses it; hosted checkout does not need a frontend secret |
| PAYSTACK_WEBHOOK_SECRET | Optional override; must match the Paystack account secret used for signature verification, or leave unset for the existing fallback |
| RESEND_API_KEY | Audit backend and Render backend |
| EMAIL_FROM | Verified application sender address; current default noreply@holygrills.online must actually be verified |
| EMAIL_FROM_NAME | Holy Grills (or configured sender name) |
| ONESIGNAL_APP_ID | Audit backend/Render; same OneSignal app as frontend |
| ONESIGNAL_API_KEY | OneSignal app REST key; server only |
| FRONTEND_URL | https://holygrills.online for live link checks; use the actual audit frontend URL for isolated payment-return tests |
| AMBASSADOR_SYSTEM_ACTOR_ID | Optional active super-admin profile UUID for automatic ambassador milestone authorization; backend/runner only |

Audit environment variables affect the audit process. They do not automatically update Render. Render variables affect the deployed backend. Most must be present when each process starts; restart/redeploy the relevant process after editing.

Frontend public build variables belong in Vercel (or the actual frontend host), and the frontend must be rebuilt:

- VITE_API_BASE_URL=https://holy-grills-backend.onrender.com/api (or the deliberate isolated audit backend URL)
- VITE_ONESIGNAL_APP_ID=the same app ID as backend ONESIGNAL_APP_ID

Never put service keys, Cloudinary secrets, Resend keys or OneSignal REST keys into VITE_ variables.

### Provider dashboards and settings

- Paystack TEST webhook: https://holy-grills-backend.onrender.com/api/webhooks/paystack only when that backend is intentionally configured for the same test account. Otherwise use the reachable isolated audit-backend webhook URL. Do not redirect the production account's webhook or swap production credentials merely to run an audit.
- OneSignal: web origin/service-worker setup must match the actual frontend domain; email approval and verified sender/domain are required before email tests can pass.
- Resend: application sender/domain must be verified.
- Optional Brevo Auth SMTP: configure in Supabase Authentication Email/SMTP settings, not Vercel/Render app variables. Host smtp-relay.brevo.com, port 587, Brevo SMTP login and SMTP key, verified sender/domain. This changes Supabase Auth delivery, not application mail routing. Allow smtp-relay.brevo.com in the audit environment only if a direct SMTP connectivity check is specifically needed; Supabase itself connects to it for Auth emails.
- Supabase Auth site/allowed redirect URLs must match the frontend used for verification/reset. Leave unrelated authorized URLs intact.
- Do not deploy external cron, Celery/Redis or migrate hosts in this verification chat: the user requested discussion only so far. Missing worker execution is a known deployment decision, not permission to start every scheduled production task. REDIS_URL/CELERY_BROKER_URL/CELERY_RESULT_BACKEND are for a later approved worker deployment.

## Ownership and existing evidence

Fresh chat owns real PWA/deployment/provider/device verification. Primary chat retains delivery/reward recovery, remaining promo combinations, durable email dispatch/counters and the broader role matrix. Do not start a competing durable-email refactor or run overlapping financial fixtures. Keep any provider-specific fix small, record files/commit and fetch main before pushing. Never force push.

Read first:

1. docs/LAUNCH_REMAINING_2026_10_28.md
2. docs/COMMUNITY_WORKSPACE_BATCH_LAUNCH_CHECKPOINT_2026_10_28.md
3. docs/PWA_CRITERIA_EVIDENCE_2026_10_28.md
4. docs/PROVIDER_VERIFICATION_BLOCKERS.md (older blocker descriptions; superseded where stated above)
5. docs/NOTIFICATION_LINK_WORKER_EVIDENCE_2026_10_28.md

Do not read the uploaded skills folder: user deferred that UI work. Cloudinary is the only image provider. Database cleanup remains paused. Preserve the user's real menu/reward/review/storefront records. No secrets in output, commits, screenshots, screenshots of admin secret fields, HARs or evidence documents. Redact guest claim tokens and signed tracking URLs from published evidence.

## Verification order

1. Fetch current main; inspect local changes before merging. Verify only presence/readiness of secrets and exact network reachability. Report missing bindings without printing values. Verify Paystack mode without exposing its key.
2. PWA: use the committed diagnostic on the deployed domain, then inspect actual Android/desktop Chrome when available. Verify real served build, redirects, HTTPS/certificate, manifest response/MIME/name/icons/dimensions/id/start/scope/display, worker registration/scope/MIME/update headers, CSP/mixed-content failures, clean versus returning profiles and Chrome installation state. Run `npm run build` then `python scripts/diagnose-pwa-browser.py --origin https://holygrills.online --output /tmp/live-pwa-check.json`. The local production CDP result had zero warnings/errors; native beforeinstallprompt did not fire headlessly. Do not turn a synthetic event, mobile emulation, a passing manifest or an in-app help button into proof that Chrome's native menu/omnibox works. Confirm hg-v5 worker/online manifest-refresh behavior after deployment.
3. Cloudinary: user already confirms uploads work. Do one isolated audit upload with real bytes, persist it through its intended admin section and verify decoding on the user page. Verify two slides with distinct image/copy/CTA where appropriate and uncropped contained tier icons. Do not overwrite the user's content, add Supabase Storage, or restart a full upload rewrite.
4. Paystack TEST ONLY: run PAY-01 through PAY-07 in PROVIDER_VERIFICATION_BLOCKERS.md: full-card, unpaid return/resume, exact split remainder, guest ownership/tracking/confirmation/cart settlement, signed webhook plus callback/replay, interruption recovery and wallet funding. Compare actual provider verification with database payment status, reference counts and wallet deltas; never infer paid from order-created/toast/query-string. Use isolated labeled actors/orders. Do not fake paid state on the production backend. Preserve real production webhook configuration.
5. Mail: send a bounded test to an already-authorized recipient, verify provider receipt/status and actual link behavior. Test guest confirmation/tracking in separate fresh browser profiles and reject wrong-owner/token access. Test signup verification/reset through configured Supabase Auth SMTP separately from application routing. At most TWO fresh Auth signups; reuse authorized audit accounts for other roles. If no authorized recipient is known, leave only that send check pending and continue independent checks. No customer blasts or deliberately exhausting free quotas. Explicit quota failover is already controlled-tested; durable quota counters/queue/retries are NOT implemented. Never mark those complete based on one real email. Header-bearing newsletters currently stay Resend-only.
6. Push: real permission/subscription registration, backend persistence, OneSignal external-ID identity, one authorized test recipient, provider acceptance AND device receipt/click, correct cart/order/reward target. Guest push must wait for campus selection; no false success from permission alone. Push provider acceptance is not device delivery.
7. Map/native handoff: off-campus map/search/tile loads, saved address/pin, gate fallback, rider map link opening; real WhatsApp share where a device supports it. Do not claim a browser-emulated click proves native app delivery.

Record results in docs/FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md with a table: case, actual environment/origin, executed steps, observed result, evidence, fixed commit if any, remaining action. Keep PASS/FAIL/NOT EXECUTED distinct. For every failed case, fix within this chat's provider/PWA ownership, run the regression, push the completed batch, and update the remaining checklist. If another chat may edit the same file, communicate the overlap before a broad change. Do not erase earlier evidence or call the entire ecosystem 100% tested.
