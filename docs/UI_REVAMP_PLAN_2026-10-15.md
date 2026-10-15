# Holy Grills — UI Revamp Plan (Launch Prep)

**Date:** 2026-10-15 · **Scope:** Frontend only. No backend contract changes, no feature removal.
**Method:** Full audit of every route (user panel), every custom popup/overlay, and all three
staff panels (Admin 32 sections, Kitchen, Rider), plus the PWA shell, sound system, and motion
language. Everything below is grounded in the actual code — file references included.

---

## 0. Goal in one line

One coherent, warm, campus-native look: **every overlay covers the whole screen the same way,
every page shares one visual grammar, density goes up, noise goes down** — so the app feels
intentional instead of assembled.

---

## 1. Audit findings — cross-cutting (the real root causes)

### 1.1 The overlay/scrim problem (the thing you noticed first)

There are **four different scrim recipes** live in the app right now, plus a structural bug:

| Recipe | Where it's used | Result |
|---|---|---|
| `bg-black/60 + backdrop-blur-md` | Most custom popups (SpinWheel, WalletFundModal, RegisterModal, PurchaseModal, …) | Dark blur |
| `bg-black/80`, `bg-black/80 + blur-lg` | shadcn `alert-dialog`, `drawer`, `PromoFlyerPopup` | **Darker** — the "some pages just darken" inconsistency |
| `bg-black/70 + blur-md/lg` | `ShareSheet`, `MobileProfileDrawer`, Home streak popup | Slightly different dark blur |
| `bg-foreground/50 + blur-sm`, `bg-black/40` | **Admin**: `AdminShared` Modal, `AdminKit`, `AdminUsers` drawer, `AdminSidebar` mobile scrim, `AdminAnalytics` brand modal | **Brownish, almost transparent** — staff panel looks broken next to the app |

**The structural bug ("light passes through at the top of the screen"):** overlays that render
`fixed inset-0` *inside* a Framer-Motion page wrapper get clipped to that wrapper (any ancestor
`transform` re-bases `position:fixed`). The repo already solved this once — `ModalPortal`
(portal to `<body>`) + `ModalBackdrop` exist for exactly this, and `Leaderboard`'s prizes modal
even carries a comment about it — but **13 components still render their overlays inline**:

`CampusGate`, `CheckoutKitchenClosedPopup`, `InstallPrompt`, `KitchenClosedPopup`,
`KitchenStatusBox` (schedule modal), `RewardDeliveryModal`, `FreeSideCreditModal`,
`admin/AdminShared` (Modal), `admin/ui/AdminKit`, `admin/AdminUsers` (drawer),
`admin/AdminAnalytics` (brand modal), `admin/AdminCatering` (detail modal),
`marketplace/MarketplacePurchasesPanel` (report modal), `storefront/PromoFlyerPopup`.

Any of these that opens inside an animated route = visible uncovered strips on phones.

**Native `confirm()` is still used in 18 files** (Admin sections, Profile, Addresses,
OrderDetail, OrderLocks, Squads, ScheduledOrders…) — raw browser dialogs that match nothing.

**z-index is ad-hoc:** 40 / 50 / 60 / 200 / 1080 with no scale — e.g. the profile drawer (z-60)
and modals (z-50) can invert, `InstallPrompt` uses a one-off `z-[1080]`.

**Fix — one overlay system (P0):**
1. **One scrim token**, used by every overlay in every panel:
   `--scrim: rgba(31, 10, 0, 0.72)` (brand brown-black — darkens *warm*, not grey) +
   `backdrop-blur-md`. Blur everywhere or nowhere; the non-negotiable is **same color, same
   opacity, full coverage, every time**. (Kept as blur — it's the brand's signature; phones get
   the same scrim, and blur cost is acceptable because overlays are short-lived.)
2. **Portal everything** — the 13 inline components move to `ModalPortal`; `ModalBackdrop`
   becomes the only way to draw a scrim. shadcn `dialog/sheet/alert-dialog/drawer` overlays
   re-pointed to the same token (one class change each).
3. **A brand `ConfirmDialog`** (built on the same system) replaces every native `confirm()`.
4. **A documented z-scale:** content 0 → sticky 20 → nav 40 → drawer 60 → modal 80 →
   install 90 → toast 100 → celebration 120. Applied across all files.
5. Admin scrims switch from `bg-foreground/50 blur-sm` to the shared token — admin stops
   looking like a different app.

### 1.2 The PWA / brand-icon bug (your "another icon" complaint)

`index.html` declares **two favicons** — the brand `/icons/icon.svg`, then an inline
**data-URI 🔥-emoji** icon *after it*. Browsers use the last suitable one → the Chrome tab shows
the emoji, not the brand. Also:

- `apple-touch-icon` points to an **SVG** — iOS requires PNG, so installed icons fall back to
  a generic tile.
- `manifest.json` ships **SVG-only** icons (`sizes: "any"`). A large share of Android
  Chrome/launcher builds require real **192×192 and 512×512 PNG** (incl. maskable) → default
  icon on install / app drawer.

**Fix (P0):** generate a real PNG set from the existing brand flame SVG (16/32 favicon,
180 apple-touch, 192 + 512 any, 512 maskable) with `sharp`; remove the emoji data-URI favicon;
register the PNGs in `manifest.json` and the service-worker shell list. Result: tab, installed
app, splash and shortcuts all show the flame mark.

### 1.3 Token drift — why it can feel like a "multicolor riot"

Measured across `src`:

- **68 files hardcode `bg-white`** instead of `bg-card` — on the beige `--background` this
  reads as cold grey-white patches vs warm cards, page to page.
- **49 files hardcode ad-hoc status colors** (`red-50`, `green-100`, `blue-100`, `amber-50`,
  `emerald-600`, `violet-500`…) — Kitchen and Rider introduce 5 palettes the brand never
  defined. These need semantic tokens (`.badge-success/.badge-warn/.badge-info/…`) with
  warm-tinted values.
- **Gradient overload:** `bg-gradient-cta` is simultaneously the primary button, the *active
  tab*, the *active filter chip*, the period selector, leaderboard podium numbers, rider hero,
  newsletter button… When everything is the CTA, nothing is. 
- **Radius chaos:** `rounded-xl/2xl/3xl/full` mixed freely; the CSS tokens
  (`--radius-menu-card` etc.) exist but are barely used.
- Two toast systems coexist (custom `Toaster` mounted; `ui/sonner.tsx` unused) — remove dead one.

**Fix — the "one flame" hierarchy (P1, applied in the same pass as per-page work):**
- **Gradient = THE hero CTA only** — one per view (Order now, Spin now, Claim). Everything
  else: solid `--primary` for primary actions, beige `secondary`/outline for the rest.
- **Tabs/chips/period pills** get a *quiet* active state: solid `--primary` (or ink-on-beige) +
  weight change — no gradient, no glow. Gradient stays out of controls.
- **`bg-white` → `bg-card`**, status colors → semantic badge utilities, radius → token scale
  (`rounded-2xl` cards, `rounded-3xl` heroes/modals, `rounded-full` pills, `rounded-lg`
  inputs) enforced file-by-file.
- **Glow shadow** (`shadow-glow`) reserved for the single most important element per screen.

### 1.4 Sound system — exists, barely orchestrated

`soundManager.ts` synthesizes 20 sounds (no audio files — nice). But they're wired in only
~13 places; e.g. order confirmation, reward unlock, HoF induction, tier ring upgrades, kitchen
"order ready", rider "new batch" have sounds *defined* but inconsistently triggered, and the
celebration overlay is silent.

**Fix (P2):** one **moment → sound map** (documented in the plan doc), wire the defined sounds
into their moments, add a mute affordance where sound is about to matter (spin, celebrations)
and keep the Profile toggle as master switch. No new synth voices unless a moment has none.

### 1.5 Motion & performance notes

- `hg-press` (unified press-down) exists and is good — finish adopting it where
  `active:scale-95/0.98/…` variants remain.
- Removing blur-inconsistencies + one carousel (below) also removes paint cost on Android;
  blur is the most expensive effect on low-end devices — one scrim layer instead of several
  stacked translucent layers helps.
- `prefers-reduced-motion`: add a global respect rule (confetti, idle wheel rotation, auto-scroll
  carousels pause).

---

## 2. Page-by-page plan — User panel (every route)

Format: **Find → Keep → Change.** Nothing is removed without a replacement; every change is
CSS/JSX-level unless stated.

### Home (`/`)
- **Find:** 13+ stacked sections; **two HeroCarousels on one page** (top hero + `placement="home"`
  promo carousel); three dark-gradient banners (gift, HP, newsletter) competing; order of
  sections buries "order food" intent.
- **Keep:** Kitchen Radar, HP tiles, featured carousel, reviews, catering, newsletter, mascot.
- **Change:**
  1. Merge the two carousels (hero stays; promos join it as slides or move below featured).
  2. Banner discipline: only ONE dark surface per viewport — gift banner becomes a slim amber
     ribbon (accent, not dark); HP banner keeps its gradient; newsletter goes to a compact
     beige card with accent icon (dark stays special).
  3. Section headers standardized: eyebrow + title + "see all" right-aligned (pattern exists —
     apply to all).
  4. Streak popup → portalled `ModalBackdrop` (currently inline, correct darkness but
     duplicated recipe).

### Menu (`/menu`) + ItemDetail (`/menu/:id`)
- **Find:** filter chips use gradient-when-active; `MenuItemCard`/`MenuGridCard` overlays use
  inline `bg-black/55` sold-out veils (fine, but not tokenized); detail page is long single
  column on desktop.
- **Keep:** category nav, search, quick-add flow, customization groups.
- **Change:** active chip = solid primary (no gradient); sold-out/“sold out” veil uses scrim
  token; ItemDetail gets a 2-column desktop layout (sticky gallery + options) to cut scroll;
  price + Add bar sticks to bottom on mobile (verify current behavior, standardize).

### Cart (`/cart`) & Checkout (`/checkout`)
- **Find:** checkout is 1,000 lines and the longest scroll in the app; kitchen-closed popup
  inline (light-leak risk); FreeSideCreditModal inline.
- **Keep:** entire flow, wallet split, HP redemption, scheduling.
- **Change:** group checkout into a 2-step visual shell (Delivery → Payment & review) *without*
  changing the form logic — one card per step, progress dots; portalled overlays; sticky order
  summary on desktop.

### OrderConfirmation (`/order-confirmation/:id`)
- **Find:** big moment, plain card.
- **Change:** this is the "haha, wow" slot: full-bleed warm gradient header, mascot
  celebration + confetti + `order_placed` sound (exists), ETA + track CTA prominent, HP earned
  count-up. One-screen summary, zero clutter.

### Orders / OrderDetail / TrackOrders
- **Find:** list rows fine; detail page stacks status timeline, items, payment, actions
  vertically; error banners use `bg-red-50` ad-hoc.
- **Change:** status timeline becomes the visual anchor (flame-progress rail, brand colors via
  status tokens); actions (cancel/reorder/review) into one row of quiet buttons with one
  gradient primary max; semantic error styling.

### Dashboard (`/dashboard`)
- **Find:** tier gradient card good; tiles vary in tone (some `bg-accent/10`, some plain);
  locks + referrals + challenges each their own card style.
- **Keep:** everything — it's the personal hub.
- **Change:** one grid, equal card heights, per-card single accent (icon color only); streak
  link merged into the tier card footer (kills a card); "assignments" (order locks) get a
  compact amber strip instead of a full gradient banner.

### Rewards (`/rewards`)
- **Find:** 734 lines; tabs Redeem/History; spin history, free-side credits, flash redemptions,
  challenges, graduation all compete; several `bg-white` cards.
- **Keep:** every feature (free sides, spin, flash, challenges, badges, graduation, history).
- **Change:** HP balance header compact + tier ring; **Free Side Credit** gets a proper
  "wallet chip" card (count + expiry + Use) at top of Redeem — it's currently buried;
  challenge cards unified to one anatomy (icon, title, progress, reward); flash items get a
  single "Flash" treatment with countdown chip; history tab rows unified.

### Leaderboard (`/leaderboard`)
- **Find:** strong bones (sticky rank card, podium, prize badges). Issues: period chips +
  view toggle + prizes button + countdown all in the first 100px; spin card is a grey
  afterthought even when a spin is *earned* (should be the loudest card); "Top 4 win" not
  communicated up front; prizes modal is thin text on `bg-white`.
- **Keep:** podium, sticky rank, rank-change arrows, squad view.
- **Change:**
  1. Header condenses: title row = title + countdown chip + Prizes (icon); toggles move below
     as one segmented control row (Solo/Squad + period merged when Solo).
  2. **Prize framing:** a slim "Top 4 take real rewards" ribbon under the header (static copy +
     prize badge icons) — makes winning legible without opening the modal.
  3. **Spin card:** earned state = accent gradient bed + animated wheel icon + pulsing Spin
     button; locked state = quiet outline. 
  4. Podium bars adopt medal tokens (gold/silver/bronze warm variants, not
     `muted-foreground/40`).
  5. Rank list rows: current-user row keeps ring, others drop shadows (less visual noise);
     HP flame icon single size.

### Hall of Fame (`/hall-of-fame`)
- **Find:** it's a list of dark rows — the least ceremonial page for the most ceremonial thing.
- **Keep:** data, share sheet (already portalled), year filter.
- **Change:** **plaque treatment** — each inductee as a gold-edged plaque card on the dark
  gradient bed (consistent with the tier-ring "living gold" language): tier-ring avatar ring,
  name in display font, "Top-4 finishes × N", season label; header gets a hero strip ("Legends
  of the Grill" + year); `badge_unlock`/`tier_upgrade` sound on opening your own induction;
  tap → share (already works). Empty state stays mascot-led.

### Wallet (`/wallet`)
- **Find:** fine; funding modal portalled already.
- **Change:** balance card adopts the HP-banner gradient (consistency with brand money
  surfaces); transaction rows get semantic +/- coloring from tokens; fund CTA = solid primary
  (gradient reserved).

### Marketplace (`/marketplace`, `/marketplace/:id`)
- **Find:** cards okay; report + purchase modals inline/portal mix; `bg-black/40` sold veil.
- **Change:** token scrims; listing card anatomy unified with menu cards (price row, badge
  slot); sell modal keeps fields, gets sectioned header.

### Events (`/events`, `/events/:id`, `/events/tiers/:tierId`)
- **Find:** header crowds (eyebrow+title+sub + catering CTA on one line); discover/mine toggle
  + category chips stack; cards fine.
- **Keep:** all of it.
- **Change:** catering CTA becomes a quiet "Request catering" text-link under the header (it's
  a niche action, not the page CTA); merge toggle+filters into one row on mobile (toggle left,
  chips scroll right); event detail: hero image + info chips (date/place/price) in one row,
  register CTA sticky; tier detail cards align to reward-card anatomy.

### Streak (`/streak`), Profile, Addresses, NotificationPreferences, Notifications, Referrals, OrderLocks, Squads, HpEducation
- **Find:** each is functional; inconsistencies are styling-level (bg-white cards, ad-hoc
  colors, inline confirm() in Squads/OrderLocks/Profile/Addresses).
- **Change:** token sweep + ConfirmDialog swap; Profile sections get consistent group headers;
  Referrals card already dark-gradient — keep as the page's one hero; OrderLocks rows get the
  amber "assignment" language used elsewhere.

### Static/auth: Login, Register, Forgot/Reset, FAQ, Terms, OurStory, Contact, CateringStatus, NewsletterUnsubscribe, 404
- **Find:** Login/Register are close to spec; FAQ/terms plain; 404 exists.
- **Change:** auth pages get the flame-glow header treatment (logo + one line, no big text
  blocks); FAQ uses accordion group headers with brand dividers; 404 gets mascot + single CTA.
  Low effort, mostly token sweep.

---

## 3. Panels

### Admin (`/admin`, 32 sections) — the biggest UX gap
- **Find (IA):**
  - Sidebar groups are good, but there's **no persistence of the last section** beyond the URL,
    no favorites — daily-use sections (Orders, Delivery) are 2 collapsible groups deep.
  - **The order→rider assignment flow is effectively hidden.** It lives in
    *Delivery → Batches → Create Batch*, and requires picking a window + rider + zone + manual
    order multi-select of **`ready`** orders. If an order arrives outside a window (scheduled/
    off-window), the admin looking at *Orders* has **zero affordance to assign it** — nothing on
    the order row points to Delivery. (This is exactly what you hit.)
  - Section internals drift: `bg-white` tables, ad-hoc status colors, native `confirm()`
    everywhere, `AdminShared` Modal scrim nearly transparent (`bg-foreground/50 blur-sm`),
    `AdminKit` modal same, `AdminUsers` slide-over same.
  - Global search is section-only by design — fine — but then section *titles* must say what
    they do (they do via `desc`, good).
- **Change (no backend edits):**
  1. **Assignment surfacing (the fix for your exact blocker):**
     - `AdminOrders` order rows (status `ready`/`received`) get an **"Assign"** action →
       opens the existing `CreateBatchModal` **pre-filtered to that order** (single-order
       mode, rider + window + zone). Multi-select still allows adding more orders → batch.
     - `CreateBatchModal` learns a **"No window" path**: when no window is open it lists
       scheduled/off-window orders (the data `liveApi.orders.getScheduled()` already returns)
       so an off-window order can be assigned without inventing a window.
     - *Batch splitting* stays in Delivery → Batches: add a visible "Split & reassign"
       affordance on a batch's order list (creates a second batch from selected orders —
       same `createDeliveryBatch` endpoint, just pre-filled).
     - Sidebar "Delivery" gets a **needs-attention dot** (count of unassigned ready orders —
       client-side from already-fetched lists).
  2. **Section shell consistency:** one `AdminTable` pattern (sticky header, row hover,
     status badges from tokens), one modal/confirm system (shared scrim token), ConfirmDialog
     replaces `confirm()` in all 12 admin files using it.
  3. **Sidebar:** pin/favorites row (client-side localStorage) for the 4–5 daily sections;
     groups stay.
  4. Mobile admin: header + drawer already exist; tables get card-collapse on small screens
     (pattern: Dashboard's stat cards) rather than horizontal scroll where feasible.
  5. Admin keeps the shared brand scrim/token updates from §1 — visually joins the app.

### Kitchen (`/kitchen`)
- **Find:** KDS board is solid; sticky tab bar; `bg-white`/`bg-red-50` drift; sounds defined
  (`order_status`) not wired to "new order landed"; header sound toggle exists (good).
- **Change:** status columns use semantic badges; new-order event gets a soft `push_received`
  chime + card flash (already has `flashingIds` — add sound); capacity bar color tokens;
  settings/catering tabs same card anatomy.

### Rider (`/rider`)
- **Find:** earnings hero gradient + stats grid fine; `bg-violet-500` status chip is the only
  violet in the product; header has sound toggle (good).
- **Change:** status chips → token set (assigned = brand brown or primary tint, delivered =
  success); batch card gets "call customer" as icon button with label; earnings hero keeps
  gradient (it's the page's one hero).

---

## 4. Feature spotlights

### Spin wheel
- Keep physics/easing + sounds (they're good). 
- Modal: full dark scrim via system; wheel ring gets the **tier-ring gold** rim (holy shimmer
  when a big prize is live); winning segment flash + confetti colors already brand — keep;
  add haptic + `spin_win` fanfare confirmation; result card = one gradient CTA ("Awesome →").
- Entry point on Leaderboard becomes the loudest card when earned (see §2).

### Free side credit
- Checkout modal: keep logic; new shell — gift-green? No: **accent-gold bed + gift icon**,
  sides as 2-up selectable cards (image + name), credit expiry line, single "Add free side"
  CTA. Sounds: `badge_unlock` on apply.
- Rewards page chip (§2) so credits are discoverable before checkout.

### Hall of Fame — see §2 (plaque system + induction feel).

### Leaderboard — see §2 (prize-forward header, spin card, podium medals).

### Sounds — moment map (implement + document)
| Moment | Sound |
|---|---|
| Add to cart / remove | `cart_add` / `cart_remove` (exists) |
| Order placed | `order_placed` + mascot confetti |
| Status change (user) | `order_status` |
| Spin open idle / spin / win / lose | `spin_idle` / `spin_spinning` / `spin_win` / `spin_no_win` (exists) |
| Free side applied / badge / tier up / HoF | `badge_unlock` / `tier_upgrade` |
| Rank improved | `leaderboard_up` + hips mascot |
| Kitchen new order | `push_received` |
| Rider new batch | `push_received` |
| HP transfer | existing pair |
All behind the existing master toggle; silent-mode respected (Web Audio default).

### PWA install — see §1.2 (PNG icon set, favicon fix, manifest + SW cache list, keep
InstallPrompt but portalled + token scrim).

---

## 5. Execution order (each phase ships green: `npm run build` + `typecheck` + `lint`)

| Phase | Content | Why first |
|---|---|---|
| **P0 — Overlay & icon system** | scrim token + `ModalBackdrop` adoption (13 inline components + shadcn overlays + admin scrims), z-scale, ConfirmDialog + replace 18 files' `confirm()`, PNG icon set + favicon/manifest/SW fix | You see these on every single interaction; cheapest highest-visible fixes |
| **P1 — Token sweep** | `bg-white`→`bg-card`, status badge utilities, radius scale, gradient/CTA hierarchy, quiet active states for tabs/chips | Everything after this inherits the coherent base |
| **P2 — Page pass** (in order) | Home, Leaderboard, Hall of Fame, Rewards, Events, ItemDetail/Cart/Checkout shell, OrderConfirmation wow-moment, then the rest incl. static/auth | Traffic order + the pages you called out |
| **P3 — Panels** | Admin IA (assign flow, pins, table/modal consistency), Kitchen, Rider | Staff-facing consistency; assignment flow unblocks ops |
| **P4 — Polish** | sound map wiring, reduced-motion, toast system dedupe, final QA vs `PRE_LAUNCH_QA.md` | Layered on the finished surface |

**Guardrails:** no route/API/prop changes to data flow; no feature or input removed; every
modal keeps its exact trigger conditions; each phase gets a before/after preview pass on
mobile + desktop widths.

---

## 6. Open questions (default chosen, flag if you disagree)

1. **Blur vs darken:** plan keeps *blur everywhere* with one warm-dark scrim (brand
   distinctive). Alternative: blur on centered modals only, plain dim on sheets/drawers for
   Android GPU headroom. Default: blur everywhere, revisit if low-end devices struggle.
2. **Second Home carousel** merges into the hero. If the `placement="home"` banners are a
   distinct ad product that must stay separate, they move below "How it's made" instead.
3. **Podium silver** becomes a warm bronze token rather than grey — assumed yes.
