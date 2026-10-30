# Launch audit checkpoint — 26 October 2026

Later same-day updates: [small launch batches](LAUNCH_BATCHES_2026_10_26.md) close the install-entry recovery, ordering-streak display, sidebar, icon safe-zone, event gate and progressive challenge work. The user confirms actual storefront Cloudinary uploads work. Chrome native-menu visibility on both Android and desktop remains under verification. This is not complete A–Z sign-off. Older progress documents contain both completed work and open items. An inventory, code fix, simulated provider result and live provider transaction are different levels of evidence.

## Current main integrated

Fetched and fast-forwarded to `f08197b` before fixing the newly reported guest regression. Preserved the earlier audit edits while merging the new email, analytics, guest-session, payment-return and cart-persistence work. Preserved the user's existing hero/layout changes; no square homepage hero or image-provider replacement.

Recent incoming changes: `09aee2a` email implementation; `4d7a19e` email analytics; `208112d` manual deliverability checks; `f8533c4` guest/payment/cart changes; `dd146ef` guest session isolation. These are integrated source changes, not independently certified live behavior.

## Fixed and checked in this checkpoint

| Area | Result and actual evidence |
| --- | --- |
| Guest payment return | Confirmation now reads the current tab's receipt; new guest Paystack callbacks carry the specific claim token in a URL fragment. Backend still verifies ownership/token and payment. URL success flags cannot mark an order paid. |
| Guest tracking emails | Initial emails now contain the full order UUID. Legacy eight-character identifiers resolve only with their full private token. Displayed order-number and full UUID lookups retain backend token/owner guards. |
| Shared devices | Receipt capabilities now live in sessionStorage. No enumeration of other tabs' persisted history and no shared legacy-history fallback. Explicit email links still work on a fresh device. |
| Cart/payment recovery | Pending guest payment retains the cart. Verified paid orders remove only their submitted, unchanged cart rows; new/edited items survive. The open checkout polls bounded verification and retries on focus for methods that do not return. An unchanged unpaid cart reuses its saved order on retry. |
| Order claiming | Successful account linking removes only this tab's receipt. Existing transactional ownership/payment restrictions remain. |
| Rich blasts | Rich fields were being dropped by the request whitelist. Validation, image/CTA/HTML sanitization, escaped personalization, audience validation and push images are now connected. Test send is restricted to the verified current admin. Provider delivery remains unverified here. |
| Delivery windows | Recurring rows with no absolute timestamp are materialized in Africa/Lagos time. Public/kitchen consumers share the schedule. No invented 18:00–19:00 confirmation fallback. |
| Production delivery configuration | Applied seven 19:30–20:30 weekly windows to FUTA and seven to Lagos; verified seven distinct weekdays per campus and all seven existing FUTA ordering links. Historical/date-specific and audit-campus rows preserved. |
| Push registration | Restored verified user initializes/identifies OneSignal v16. Single-flight init, bounded failure, v16 opt-out, no page-load prompt, soft prompt closes after failed registration. Controlled native browser and SDK tests pass. |
| Admin/user controls | Promo menu-item picker, private campus-bound squad student selection, debounced search pending state, and wallet/HP debit-credit direction fixes. Unit/type/lint coverage; complete native admin action coverage remains open. |
| Email outcomes | Resend needs a provider message ID. OneSignal needs a message ID and positive recipient count; zero recipients no longer means success. Existing explicit-quota failover retained; ambiguous outcomes do not trigger speculative duplicate sends. Accepted is not proof of inbox delivery. |
| Rewards display | Prevented a numeric zero from leaking through a JSX conditional before a flash price. Broader reward-editor economics mismatch remains open below. |
| Build | Fixed missing AdminEvents busy state and case-conflicting Skeleton filenames while preserving the new visual component. |

### Executed checks

- **186 targeted backend tests passed**, covering guest claims/tracking, payments, rich blasts, squad privacy, delivery windows, ordering state, email fallback/preferences, roles, batch transactions, delivered HP, reward checkout/release gates and order contacts/summaries. This is not a claim that every backend test was run.
- Six controlled Playwright guest routes passed: paid return/current-tab token; fresh-context fragment; pending-to-paid cart settlement; other-tab history ignored; email auto-lookup; checkout left open without provider redirect. No real accounts, charges or emails were created.
- Frontend TypeScript, changed-file ESLint and complete production build passed.
- Guest receipt/cart helper checks, ten ledger direction cases and OneSignal v16 SDK tests passed.
- Local production Chromium, **persistent normal profile**, reported **no installability errors**. Manifest icons returned 200 with declared PNG dimensions matching 192/512; service worker active/controlling. The initial incognito diagnostic produced only `in-incognito`, resolved by testing a normal profile. This is not a deployed-domain installability result.
- Controlled push browser: restored user identified without prompting; explicit enable reached device-token endpoint; simulated backend 503 closed the prompt.

Reproduce local guest checks from the frontend: `node scripts/test-guest-orders.mjs` and `python scripts/test-guest-payment-browser.py` (requires Python Playwright and Chromium). The latter uses controlled API responses, never a payment provider.

### Supabase changes

`20261026140956_support_validated_rich_notification_blast_content` is applied exactly once; its canonical SQL is in backend migrations. Four columns on the existing table, bounded shape checks, no new tables, existing RLS retained. The subsequent grant audit found inherited excessive table privileges. Applied `20261026193311_restrict_notification_blast_role_privileges`: verified anon has zero table privileges, authenticated has only SELECT/INSERT/UPDATE/DELETE under existing admin RLS, service_role retains worker access. The security advisor was run; existing project-wide helper/extension/newsletter findings remain in the broader security queue. Production delivery DML is journaled in `docs/PRODUCTION_DAILY_DELIVERY_CONFIG.sql`; it is configuration, not a schema migration. No database cleanup was performed.

`docs/EMAIL_DURABLE_DISPATCH_DRAFT.sql` is **not applied** and must not be run as if the queue/worker code were complete.

## Remaining work — this chat / Workstream A

1. **Live guest/payment confirmation:** actual card and bank-transfer Paystack return, webhook-before/after-return, cancellation, refresh, lost-response and duplicate checkout. Use test mode only; do not charge a live key. Check actual confirmation/tracking emails and cart recovery in the deployed browser. Current fixes have controlled browser/backend evidence, not provider sign-off.
2. **Delivery completion variants:** native off-campus map/pin, address/landmark/save-address, nearest gate and manual fallback; unknown/radius errors; multiple-order automatic groups, competing bulk assignments, unclaimed/attempted delivery, physical rewards and rider payout settlement. Earlier standard kitchen → two riders → delivered food/add-on HP proof remains valid only for its recorded cases.
3. **Money/reward combinations:** real wallet funding/split checkout; promo/order-lock/free-side/reward stacking; cancellation and partial/full refunds; exact benefit restoration and competing ledger actions. Native automatic redemption → delivery-now fee checkout or attach-next-order → physical kitchen/rider fulfillment remains open.
4. **Reward editor — repaired in batch 8:** canonical types, backend preview, fractional margin conversion, partial-cost repricing, saved-price preservation and stale-editor protection are implemented and tested without bulk changes. Remaining: complete customer redemption/physical fulfillment and historical reward cases, transfer/admin-grant loops, generalized promo campaigns and interruption recovery. Progressive challenge presentation is implemented in batch 6.
5. **Durable email dispatch:** finish reviewed queue/reservation/circuit/reset RPCs, application integration and worker retries using existing tables. Prove quota exhaustion, reset, known rejection, crash recovery, zero recipients, uncertain outcomes and no duplicates. The saved SQL draft alone is not implementation. Verify new main's analytics and email schema separately. Auth SMTP is independent; SES approval remains external.
6. **Storefront/provider verification:** actual Cloudinary byte upload and decoded artwork for every channel; independent multiple slides/copy/CTA, image-only fields and full save/reload/public reflection; signed-in/returning-session performance on the deployed domain. Existing implemented controls and previous proofs are not every possible content/role variant.
7. **Push/automation:** real-device installation/permission/bonus once-only, denied permission, real provider receipt and deep links; actual Celery/Redis schedules, disabled-at-launch multiplier/flash generation, staff advance notices and user blasts. A local SDK stub does not prove provider subscription/delivery.
8. **PWA artwork — repaired in batch 4:** complete supplied gold S regenerated with safe-zone tests. Remaining: verify installed-device appearance and the reported missing Chrome native-menu entry on Android and desktop; normal-profile local Chromium reports no installability errors.
9. **Remaining admin A loops:** every relevant order/menu/reward/promo/storefront/kitchen/rider field and action still needs role/campus/global, invalid input, retry, concurrency, persistence and consumer evidence. Inventory is not sign-off. Track open cases in the existing admin coverage/evidence matrices.

## Remaining / coordinated Workstream B

Identity and staff administration; campus/academic-calendar controls; inventory/stock/reporting/exports; catering; residual system settings/preferences; historical schema/advisor review. Event HP atomic recovery and check-in evidence must be reconciled with B's actual commits/proofs before claiming completion. Marketplace/events broad exploration remains deferred behind launch ordering work. No completion is inferred merely because another chat owns the area.

## Access limits for the next environment

The current running environment still allows Render and Supabase but blocks the live frontend and payment/email/media providers. User explicitly said to continue accessible checks and record this for the next chat; do not repeatedly ask for the allowlist. Test `https://holygrills.online` from a fresh environment. Never call local browser checks a live-site pass.

No new signup accounts, provider emails, blasts or real payments were created in this checkpoint. The uploaded task's maximum-two-plus-address signup budget remains unused.

## Direct answers

- The reported missing confirmation/cart behavior is a flow bug, not an expected consequence of a Paystack test key. A successful bank/card payment must reach the same verified confirmation state.
- A guest email link contains a bearer capability: someone with that exact valid link can access that order. Session isolation prevents automatic cross-session discovery; it cannot prove the recipient's identity. Wrong-order/missing/revoked tokens must fail. Stronger recipient identity would require a separate verification step.
- Supabase normally sends Auth verification/reset through its configured email/SMTP service. Application provider fallback does not automatically apply to those messages.
- Recommended application routing remains transactional receipts/payment and important guest delivery updates through Resend, promotional/newsletter/challenge nudges through OneSignal. Actual inbox placement is not guaranteed by either provider. Application quota rejection can switch providers; durable global counting/queued retry is still open.
- Audit documents include completed fixes as an evidence history. The numbered sections above are the outstanding queue; do not count every old progress-log entry as an unfixed bug.
- To refresh an installed app after deployment: close all app/browser windows, reopen while online, then reload. If stale assets remain, clear only this site's browser data/service worker and reinstall; doing so removes saved local guest receipts, so preserve tracking emails first. A normal deployment should not require routine cache clearing.

Database cleanup and the uploaded UI-skills exploration remain paused by the user.
