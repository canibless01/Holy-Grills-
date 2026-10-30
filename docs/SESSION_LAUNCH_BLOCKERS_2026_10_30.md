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
| Order notification deep links | IN PROGRESS; short display ID incorrectly beat full reference UUID in default URL; fix and regression added |
| Orders screen active order plus “No orders yet” | IN PROGRESS; empty state was testing only past orders; fix added |
| Push logo and clearer delivery copy | IN PROGRESS; payload lacked browser icon; explicit public brand icon added. Native notification layout remains OS-controlled |
| Welcome free side / signup eligibility | INVESTIGATING; live global config enabled, one credit / 60 days. Confirmed mailbox account received a signup credit and has zero remaining; tracing consumption. A different fresh account needs its email/ID |
| Exclusive spins | INVESTIGATING UI errors versus genuine eligibility; no default signup/monthly spin allowance exists in the configured tier rules |
| Wallet top-up 50 HP | IN PROGRESS; matching account has qualifying ₦10,000 and ₦3,000 top-ups without HP. Paystack string was passed into UUID HP reference; stable wallet transaction UUID fix added. ₦1,000 is below configured ₦3,000 threshold |
| Profile reward count failures shown as zero | TODO; distinguish unavailable/loading from real zero and retry reads |
| Google Maps migration / checkout map failures | IN PROGRESS; browser key not in managed environment; requested Maps JavaScript API + Places API (New), billing and restricted key in Vercel. Preserve address/gate fallback and server pricing |
| Checkout slow location / quote Retry / disabled submit | INVESTIGATING; independent reference loads bundled in Promise.all, quote has generic 12-second deadline. Never bypass server-verified quote or retry charge/order mutations |
| Delivery gate selector with missing data | TODO; show valid campus data or actionable state, preserve valid manual-address path |
| Kitchen loading failures | INVESTIGATING; seven API reads in one Promise.all let ancillary failure block the workspace |
| Today's kitchen queue / older backlog / newest ordering | TODO; separate today's work from older unfulfilled orders without hiding or deleting backlog |
| Ordering cutoff versus delivery window | TODO; preserve server cutoff/scheduling logic, use “ordering closed” copy and explain prep/delivery stages |
| Batch/window duplicate labels and preparation list | TODO; campus/date-aware labels/filtering; verify order → prep queue → ready → rider batch; do not silently delete audit windows |
| Untiered dashboard users | INVESTIGATING; tiers use profiles.current_tier_id, not tier_id. Check student eligibility, test/staff accounts and missing assignment separately |
| Ambassador mobile layout | IN PROGRESS; responsive cards/tabs changed to avoid fixed minimum widths/overflow |
| WhatsApp button opening image instead | IN PROGRESS; old fallback downloaded/opened Cloudinary. WhatsApp action now opens the caption deep link synchronously; graphic saving stays separate |
| OneSignal email approval | PROVIDER BLOCKED until review on/after 1 November 2026. User supplied rejection; all provider DNS verification records pass and domain is active. Need domain-mailbox OneSignal login and review readiness; no fabricated reason or approval claim |
| Namecheap DNS/mailbox | CONNECTOR LIMIT: exposed tool only checks domain availability. Inspect public DNS; no DNS-account read/write capability exposed |
| Explain admin versus OneSignal dashboard sending | TODO; app admin/automatic events → backend → OneSignal delivery; dashboard is separate manual campaign tooling. Trace exact implemented paths |
| Google Business Profile / reviews destination | TODO; site currently supports placeId but none confirmed. Need user-owned Business Profile/Place ID; do not promise automatic export of website reviews |
| Google search / brand positioning | TODO; read About/Terms/site voice, update metadata/structured data consistently with connection/community identity. Google controls recrawl and AI Overview |
| Final handoff/checklist | KEEP UPDATED; distinguish deployed/provider, controlled transport, user/device and blocked checks |

Current evidence: `docs/evidence/deployed-recovery-2026-10-29/`. Original provider results remain in `FRESH_ENV_PROVIDER_PWA_RESULTS_2026_10_28.md`; newest applicable results supersede historical failures.
