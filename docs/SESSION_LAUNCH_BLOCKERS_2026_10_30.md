# Holy Grills session checklist — 30 October 2026

Preserve customer/admin content and concurrent main changes. No database cleanup, scheduler deployment, broadcast, hosting migration or new payment fixtures. Reuse labeled audit actors. User expanded the scope below after the original handoff; earlier ownership boundaries do not prevent these requested fixes.

| Work | Current status / evidence |
| --- | --- |
| Review current main and preserve concurrent work | DONE; integrated through `8d0938a` before latest push; always fetch before the next push |
| Vercel canonical host / OneSignal origins | DONE; apex serves directly, www redirects to apex, Chrome/Safari origins agree |
| Storefront return cache and SSR exit | DONE; original implementation retained, full builds exit 0, controlled failures pass |
| Bounce guard after URL cleanup / blocked storage | FIXED `c88a3c6`, 53 canonical assertions pass |
| OneSignal configuration script blocked by CSP | FIXED `be160cc`, real deployed SDK initialization passes |
| Shared PWA / SDK worker repeatedly reloading the page | FIXED `c99ac60`, deployed through `da8299a`; real signed-in desktop/mobile observe the SDK worker switch and retain document/cache; 143ms / 128ms returns |
| PWA technical prerequisites | PASS desktop/mobile headless; native install entry remains a device check |
| Actual push receipt | USER CONFIRMED; disabling Chrome ad blocker helped. Screenshot shows actual order confirmation. No additional send necessary |
| Order notification deep links | FIXED; new notifications use full reference UUID; old short links resolve only against owned orders/private guest capabilities. Regression tests pass |
| Orders screen active order plus “No orders yet” | FIXED; empty state requires no active or past orders; failed reads have retry and account changes reload safely |
| Push logo and clearer delivery copy | FIXED source; explicit browser brand icon, readable date and 12-hour delivery times. OS notification layout and icon caching require device confirmation after rollout |
| Welcome free side / signup eligibility | VERIFIED; confirmed account was granted one signup credit on 25 October, used 26 October 21:06 UTC; related order includes free Grilled Plantain. Zero remaining is valid; no duplicate grant |
| Exclusive spins | VERIFIED; feature enabled but current tier rules grant zero monthly spins. Enabled feature does not grant a spin automatically; read failures now display Unavailable rather than false zero |
| Wallet top-up 50 HP | FIXED source and owner recovery; stable wallet receipt UUID, flat 50 active HP, no multiplier. Verified both Paystack TEST payments and recovered 100 active HP; wallet money unchanged. ₦1,000 remains below ₦3,000 threshold |
| Profile reward count failures shown as zero | FIXED; separate loading/unavailable states and retry for sides/spins |
| Google Maps migration / checkout map failures | IMPLEMENTED; single SDK load, basic zoomable map, tap/drag pin, Places (New), GPS/gates, server fee calculation retained. Controlled browser interactions pass. LIVE GOOGLE BLOCKED until restricted VITE_GOOGLE_MAPS_API_KEY is set and deployed |
| Checkout slow location / quote Retry / disabled submit | FIXED source; independent delivery reference loads render separately, obsolete quotes cancel, read-only quote gets bounded longer timeout and one transient retry. Never retries order creation or charges; live slow-network ordering still needs user check |
| Delivery gate selector with missing data | FIXED; data remains campus-scoped and missing/failed reference data has an actionable message/retry |
| Kitchen loading failures | FIXED; critical queue renders before secondary reads, ancillary failures warn separately, details refresh every 30 seconds, overlapping polls skipped. Concurrent stock/prep safeguards retained; controlled browser tests pass |
| Today's kitchen queue / older backlog / newest ordering | FIXED; today is default, older/undated unfulfilled work is a separate visible tab; newest first; timers compact days/hours |
| Ordering cutoff versus delivery window | FIXED copy; ordering cutoff remains server-enforced, distinct from later preparation and delivery. “Ordering closed” replaces misleading “kitchen closed” text |
| Batch/window duplicate labels and preparation list | FIXED source; only eligible campus windows with paid ready unassigned orders shown; labels include campus/date/ID. Kitchen prep list aggregates preparation; rider batches are assigned after ready. Concurrent stale-summary/write controls pass browser test |
| Untiered dashboard users | FIXED; verified 11 missing active-student assignments. Owner HP recovery recalculated one tier; bounded helper assigned remaining ten, preserving points/existing tiers. Signup/account restore fills missing eligible student tiers; staff excluded |
| Ambassador mobile layout | FIXED source; tabs wrap and cards use responsive grids. Broad real-device visual sign-off remains useful |
| WhatsApp button opening image instead | FIXED; opens wa.me composer synchronously with personalized caption/link; test exercises actual helper. Save graphics remains separate |
| OneSignal email approval | PROVIDER BLOCKED until re-evaluation on/after 1 November. Confirmed exact login support@holygrills.online; all domain DNS checks passed. Generic rejection does not reveal private approval reason; renaming mailbox is not an evidenced fix |
| Namecheap DNS/mailbox | VERIFIED public MX uses Namecheap forwarding; SPF includes OneSignal and Namecheap forwarding, DKIM/tracking resolve. Paid mailbox not inherently required if forwarding receives mail. Connector cannot inspect/edit DNS account |
| Explain admin versus OneSignal dashboard sending | VERIFIED; admin manual sends and automatic app events call backend notification service, which dispatches to OneSignal push. OneSignal dashboard can also create separate manual campaigns; it is not required for each app event. Email routing is separately configured; Resend test acceptance does not prove OneSignal email approval |
| Google Business Profile / reviews destination | IMPLEMENTED neutral voluntary CTA for all ratings; needs user-owned Business Profile Place ID as VITE_GOOGLE_BUSINESS_PLACE_ID. Website reviews cannot automatically become Google reviews |
| Google search / brand positioning | FIXED source; homepage, primary/OG metadata and Restaurant JSON-LD now emphasize friendship/shared plates/campus connection consistent with Our Story. Google controls recrawl and AI Overview; Search Console indexing request remains owner action |
| Final handoff/checklist | KEEP UPDATED; distinguish deployed/provider, controlled transport, user/device and blocked checks |

Current evidence: `docs/evidence/deployed-recovery-2026-10-29/`. Original provider results remain in `FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md`; newest applicable results supersede historical failures.

Additional requested work:

| Work | Status |
| --- | --- |
| Menu / checkout / admin / kitchen duplicate reads | Shared in-flight JSON GET requests across callers, scoped by account/session/campus/headers/deadline; entries removed after completion/error. Controlled transport tests prove scope isolation and fresh retries. No persistent private-response cache or mutation coalescing. Kitchen also reduces secondary polling. Further page-specific profiling remains possible; no blanket latency claim. |
| Hall of Fame “Test User F” | Stored `[TEST] userf` induction with three finishes, not hardcoded UI. Public Hall of Fame API excludes explicitly labelled test/audit entries, preserving diagnostics. Ordinary names such as Testimony remain visible. |
| Guest email tracking | Actual production mobile browser opened existing canidesigns@gmail.com guest order using full UUID; live API also accepts its short ID and order number with private token. One labelled tracking-check email accepted via Resend; recipient inbox/click confirmation pending. No new order/payment needed. |
| Other HP references | Reviewed active-award call sites: order/redemption/event/grant IDs are UUIDs; recurring grants use deterministic UUIDs or no reference. No second Paystack-string/UUID mismatch identified in those call sites; this is not an exhaustive historical ledger recovery. |

Validation: final integrated backend suite **788 passed**; delivery-copy regression included. Frontend typecheck/full build and controlled Google Maps, request sharing, WhatsApp and kitchen action checks pass. No new schema migration or scheduler job deployed. Evidence: `docs/evidence/launch-blockers-2026-10-30/`. Source commit/deployment verification is recorded below when completed.

Remaining external dependencies: Google browser key and real-provider Maps test; owned Google Business Profile Place ID; OneSignal approval re-evaluation from domain login on/after 1 November; recipient/device confirmation of email link and branded notification appearance. Google recrawl cannot be guaranteed.

## Deployment boundary

Frontend source through `14be33b` deployed READY as `dpl_7xSs7n8yn4nnFj4fHcnEscCSx3TZ`, with production apex aliases. Live homepage includes new community copy; production CSP explicitly allows Maps JavaScript/Places hosts and retains OneSignal config scripts. The later frontend Hall filter also suppresses labelled fixtures if an older API returns them.

**Backend rollout is still required/needs confirmation.** The live Render Hall endpoint still returned `[TEST] userf` after the frontend deployment, so a Git push alone does not establish backend rollout. No Render deployment credential/connector or backend deployment workflow is available in this environment. Deploy the latest main commit to the existing Render service (no migration or schema change), then verify the public Hall endpoint excludes labelled fixtures and the next qualifying top-up awards exactly 50 active HP. New notification UUID/icon/readable-copy and initial-tier prevention fixes likewise require that backend deployment. The bounded 100-HP recovery and existing student-tier repairs were applied directly through the validated service path and are already reflected in the database.

Other remaining confirmations: recipient clicks the single tracking-test email; actual device renders updated branded notification after backend rollout; real Google map loads/searches after the configured key is deployed. Existing live guest tracking already passed full UUID, short UUID and displayed-number resolution with a private token.
