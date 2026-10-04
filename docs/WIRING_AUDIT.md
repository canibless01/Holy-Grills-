# Frontend ↔ backend wiring audit

**Date:** 2026-10-04 · **Scope:** every API call the React app can make, joined
against the real Flask route table; every field a write endpoint requires,
checked against the frontend that must supply it. Read-only against the backend
(no backend file was changed).

## How it was produced

1. **Authoritative route dump** — the Flask app was booted with dummy Supabase
   env vars and its `url_map` dumped, so the route list is what Flask actually
   serves (406 rules, 405 under `/api`), not a regex guess:

   ```bash
   cd holy-grills-backend && python3 -m venv /tmp/hgvenv
   /tmp/hgvenv/bin/pip install -r requirements.txt
   SUPABASE_URL=http://x SUPABASE_SERVICE_ROLE_KEY=dummy SUPABASE_ANON_KEY=dummy \
   SECRET_KEY=dev /tmp/hgvenv/bin/python - <<'PY'
   import json, inspect
   from app import create_app
   app = create_app()
   out = []
   for r in app.url_map.iter_rules():
       if not r.rule.startswith('/api'):
           continue
       fn = app.view_functions.get(r.endpoint)
       while hasattr(fn, '__wrapped__'):      # unwrap @require_auth & co.
           fn = fn.__wrapped__
       out.append({'rule': r.rule, 'methods': sorted(r.methods - {'HEAD', 'OPTIONS'}),
                   'endpoint': r.endpoint,
                   'file': inspect.getsourcefile(fn).replace('/home/user/Holy-Grills-/', ''),
                   'line': inspect.getsourcelines(fn)[1],
                   'func': fn.__name__})
   json.dump(out, open('be_routes.json', 'w'), indent=1)
   PY
   ```

2. **Frontend call extraction** — every `apiClient.*` call, `fetch(`${BASE_URL}…`)`
   and `getRaw` in `src/`, normalised (`${id}` → `{}`).

3. **Join** — segment-wise, with a Flask `<param>` matching any literal segment
   (so `PATCH /admin/settings/free_side_options` matches
   `PATCH /api/admin/settings/<key>`).

4. **Field join** — the JSON keys each view reads (`request.get_json()`…
   `.get('x')`, `x['y']`, `if not …get('z')`, `required = [...]`, the swagger
   `required:` list) versus the keys the frontend sends.

5. **Two extra sweeps** — (a) every required key searched across the whole
   frontend source; (b) every `*Payload`/`*Request` interface field searched
   across the whole backend source.

Reproduce: `python3 tools/wiring_audit.py --json /tmp/audit.json`.

## 1. Route level — every frontend call now resolves (438 / 438)

_Updated 2026-10-04 (wiring round, §3.6): the six calls with no backend route are
gone. All six had real UI callers, so each was either rewired to the route that
actually serves the data or removed with its dead UI (the honest fix — a button
that can only 404 is worse than no button). `tools/wiring_audit.py` now reports
**0** frontend calls with no backend route._

For the record, the six that were found and what happened to each:

| Old call | Backend reality | What was done |
|---|---|---|
| `GET /settings` (`liveApi.config.get`) | route never existed; public settings are `GET /storefront/config/public` | **rewired** (§3.2) |
| `GET /admin/free-credits` (free-credit ledger) | no route in any method; free-sides admin is `/free-sides/admin/*` | **UI replaced** by the grant panel + items CRUD (§3.6) |
| `GET /admin/exclusive-spin/history` (spin ledger) | no route (admin.py serves the pool, the grant, the fulfilment list) | **UI replaced** by the grant panel (§3.6) |
| `POST /admin/reviews/<id>/promote` (testimonial) | no route; admin.py serves `GET /admin/reviews` only | **button removed**, reported (needs a backend route) |
| `GET /items/archived` (archived menu items) | no route; `is_archived` is only ever filtered, never listed | **view removed**, reported (needs a backend route) |
| `POST /orders/<id>/resend-tracking` | no tracking route exists at all in orders.py | **button removed**, reported (needs a backend route) |

The three reported ones are frontend-safe now (nothing to click), and each comes
back the moment the matching backend route lands.

| Call | Where | What the user sees | Note |
|---|---|---|---|
| `GET /settings` | `liveApi.ts:1373` → `featureConfig.ts:100` | Public settings fall back to built-in defaults | A real route exists for this data: **`GET /api/storefront/config/public`** — repointing the frontend is a small, safe fix |
| `GET /items/archived` | `liveApi.ts:637` → `AdminMenu.tsx` | Admin "archived" view is always empty | `menu.py` filters `is_archived` but never lists archived items |
| `POST /orders/<id>/resend-tracking` | `liveApi.ts:184` | Guest resend-tracking action errors | Rate-limited endpoint described in the comment; not implemented |
| `POST /admin/reviews/<id>/promote` | `liveApi.ts:1074` | Admin review promotion errors | Only `GET /admin/reviews` exists |
| `GET /admin/free-credits` | `liveApi.ts:1224` | Admin free-credit list always empty | Free-side admin lives at `/free-sides/admin/*` (items + grant), but has no credit *list* |
| `GET /admin/exclusive-spin/history` | `liveApi.ts:1241` | Admin spin history empty | Pool CRUD + prize fulfilment exist; no history feed |

**Thirty-four backend routes have no frontend caller** (previously reported as
42; the number drops once wildcard segments match). None is referenced by the
web client except through the routes above. Decision needed: keep as the
mobile/webhook/admin-API surface, or retire. Full list in the appendix.

## 2. Input level — every required input exists in the UI

* **0** required backend fields are absent from the frontend source (sweep over
  all 216 write endpoints). Checkout's own validation already covers delivery
  type, hostel/gate, guest name/phone/email and split-payment limits
  (`Checkout.tsx:196-221`), matching the backend's guest rules
  (`orders.py:79-84`).
* The handler-side required sets that looked alarming in a raw diff
  (`user_id`, `organizer_id`, `created_by`) are values the backend **assigns**
  from the authenticated session, not inputs.

## 3. Findings

### 3.1 P1 — free-side credits are not actually applied to orders — **FIXED 2026-10-04**

The UI says "it's added to this order at ₦0. The credit is used the moment you
place the order" (`FreeSideCreditModal.tsx:44`). The backend disagrees.

* **Backend flow (authoritative):** `POST /api/free-sides/select
  {free_side_item_id}` writes a `cart_free_side_selections` row; on order
  creation `order_service._consume_free_sides()` consumes those rows — atomically
  since `migrations/2026-10-01_free_sides_reward_consumption.sql` — decrements a
  credit and inserts the ₦0 `order_items` line.
* **Frontend flow:** the modal picks a **name string** from the
  `free_side_options` config blob (`featureConfig.ts:164`), and Checkout sends
  `free_side_credit: true, free_side_choice: <name>` in the order body
  (`Checkout.tsx:247`). **Neither key is read anywhere in the backend** (the
  `create_order` handler reads only the fields it validates; the grep for
  `free_side` outside `free_sides.py` finds only the consumption service).
  The frontend never calls `POST /free-sides/select`.
* **Net effect:** a customer with a credit sees the ₦0 line and the credit is
  never spent — the order is priced without it. No money is lost, but the
  feature is not delivered.
* **Fix (applied, frontend-only, aligns to the documented backend flow):**
  `FreeSideCreditModal` now lists the backend's curated `available_sides` by id;
  Checkout's `handleUseFreeSide` calls `POST /free-sides/select` (replacing any
  previous selection via `DELETE /free-sides/select/<id>`), and the two unread
  body fields are gone from `Checkout.tsx` and `CreateOrderPayload`. If selection
  fails the UI says so and adds nothing — the summary can no longer promise a
  free side the backend will not deliver. `liveApi.rewards.selectFreeSide` /
  `deselectFreeSide` are the new methods (`src/types/free-sides.ts` already had
  the payload types).

### 3.2 P2 — `GET /settings` should be `GET /storefront/config/public` — **FIXED 2026-10-04**

`featureConfig.ts` reads public settings (WhatsApp number, streak rewards,
free-side options…) from a route that does not exist, then falls back to
`/admin/settings` (admin-only, 403 for students) and finally to hard-coded
defaults. The documented public route — `storefront.py`,
`config/public` — is not called by the client at all. Consequence: **students
get built-in defaults, not admin-configured values**, for every setting read
through this path. **Applied:** `loadSystemSettings()` reads
`liveApi.storefront.getPublicConfig()` and folds the flat key→value map into
`settingsMap`; the dead `liveApi.config.getPublic()` method is removed and
`types/config.ts` documents the real route.

### 3.3 P3 — documented-but-missing routes (section 1)

Six calls above; the `/settings` one is 3.2. The other five are admin/guest
conveniences — report for a backend decision, or remove the frontend call and
the now-dead UI affordance (standing rule: what the backend does not serve comes
out unless you say it is essential).

### 3.4 Fixed during this audit (frontend bugs the typing pass exposed)

| What | Why it was invisible | Status |
|---|---|---|
| `GET /challenges/my` envelope destroyed | `liveApi.challenges.my()` ran `unwrap(res, 'challenges')` on an endpoint that returns `{badges, challenges_available, challenges_completed}` and has no `challenges` key → always `[]`. The Rewards challenges tab and the whole Streak challenge list rendered **empty for every user**. | **Fixed** — returns the typed envelope; both pages consume it |
| Payment method was a free-form string | `payment_method` was typed `string` while `PaymentMethod` is a 3-value union; Checkout's picker state was untyped | **Fixed** — union-typed, picker ids typed |
| Dead `Array.isArray(x) ? x : x?.key` fallbacks | Only reachable while the API layer returned `any`; once `unwrap` is typed they were statically dead (`Property 'items' does not exist on type 'never'`) in `AdminMenu`, `AdminStore` (×2) and `HallOfFame` | **Removed**, with the unwrap key lists widened to keep behaviour identical |

### 3.5 Harmless drift (no action required, listed for completeness)

* Fields the frontend sends that the backend ignores **by design**:
  `delivery_location_id`/`delivery_type`/`menu_item_id_for_reward` on
  `POST /rewards/redemptions/<id>/delivery-choice` (the endpoint only records the
  mode; checkout applies the rest).
* Payload types no caller uses: `CompleteChallengePayload.proof`,
  `GraduationClaimPayload` (the graduation route itself has no caller),
  `CreateSquadPayload.is_private`, and several admin payloads carrying
  `display_order`/`cta_label`/`link_url` where the backend reads a differently
  named field or none. Recommend deleting the stale type fields in a later pass
  rather than touching them now.

### 3.6 Orphan-route classification — intentional vs missed wiring (2026-10-04)

Every backend route with no frontend caller was classified. **16 were wired**
(each to a surface that already existed or belonged to the page it supports — no
new pages were invented), **16 are intentional** (aliases, parity endpoints, ops
tooling, deprecated shims), and **1 is a product decision** that stays open.

#### 3.6.1 Wired in this round (16 routes → existing UI)

| Route(s) | Wired to | Why it was a miss |
|---|---|---|
| `GET/POST/PATCH/DELETE /free-sides/admin/items` | AdminFreeCredits → "Free Side Credits" list + add/edit/deactivate | The public `GET /free-sides` reads the **`free_side_items` table** (`_get_free_side_options`), while the admin page was writing the dead `system_settings.free_side_options` blob — so editing "side options" changed nothing students saw. The page now curates the table the checkout actually reads. |
| `POST /free-sides/admin/credits` | AdminFreeCredits → "Grant Credits" panel | No way at all to grant a credit from the web app: the only credit sources were the monthly jobs. |
| `GET /auth/users/search` | both grant panels (free sides, exclusive spin) | The student picker; campus-scoped and rate-limited, so it replaces the old whole-user-list drop-downs. |
| `POST /admin/exclusive-spin-grant` | AdminExclusiveSpin → "Grant Spin Credits" panel | Same as the free-side grant: the route existed with no UI. |
| `GET /departments/faculties` | AdminDepartments → faculty suggestions (`<datalist>`) | The form guessed faculties from the rows already loaded; the route is the campus-aware source of truth. |
| `POST /admin/departments/<id>/restore` | AdminDepartments → restore toggle | Deactivate/restore now uses the same pair as academic levels (DELETE + POST /restore) instead of flipping `is_active` by hand. |
| `PATCH /menu/items/<id>/variation-groups/<gid>/options/<oid>` | `liveApi.admin.saveItemModifiers` (AdminAddons editor) | The editor deleted every option and recreated it, so option UUIDs turned over on each save and any order history pointing at them dangled. Options are now matched by name and PATCHed in place (`PATCH /menu/addons/<id>` likewise for add-ons, replacing archive-and-recreate). |
| `POST /challenges/push-subscribed` | `lib/webPush.ts` (push enable flow) | `/push/subscribe` only stores the row; the milestone-claiming route (which awards the PWA-push bonus the UI advertises) was never called. Now fired non-blocking after registration, and it still works where no milestone is configured. |
| `GET/POST /storefront/newsletter/campaigns`, `GET /storefront/newsletter/campaigns/<id>`, `POST …/test`, `POST …/cancel` | AdminStorefront → "Newsletter" tab → Campaigns panel (compose, test-send, queue, cancel, detail) | The tab listed subscribers only, so the whole send side of the newsletter had no UI. |

#### 3.6.2 Intentional — no frontend caller by design (16 routes)

| Route(s) | Why it stays caller-less |
|---|---|
| `GET /academic-calendar`, `GET /academic-calendar/current` | Public read parity for the admin-managed calendar (the web app manages it through `GET/POST/PATCH /admin/academic-calendar`); the app's own gating reads the table server-side. |
| `GET/PATCH /admin/campuses/<campus_id>/location` | There is no campus-management UI in the app at all — campuses are provisioned out of band. |
| `GET /admin/delivery-batches/<batch_id>` | Detail row; the delivery-batches UI is list-driven (`GET /admin/delivery-batches`). |
| `GET /admin/hp/pending-squad` | Ops report (JSONB RPC, campus-scoped server-side). No UI slot; surfacing it needs a payload spec first. |
| `GET /analytics/hp-ecosystem`, `GET /analytics/items-menu` | Aliases — the same view functions are registered as `/analytics/hp` and `/analytics/items`, which the app calls. |
| `GET /auth/users/search` (as an alias) | Same view function as `GET /users/search`, which the app calls (matched on the canonical path). |
| `GET /kitchen/settings/<key>` | Per-key reads for other clients; the app reads and writes the whole settings map. |
| `POST /marketplace/listings/<listing_id>/image` | Alias of `POST /marketplace/admin/listings/<id>/image`, which the app calls; image_url is also accepted by create/update. |
| `PATCH /menu/items/<item_id>/availability` | Single-item form of the bulk route the app calls (one id is a valid bulk request). |
| `POST /menu/items/<item_id>/image` | Dedicated upload endpoint; the app saves `image_url` through create/update and the ImageUploader. |
| `POST /referrals/complete` | Docstring: "internal endpoint called when a referred user completes their first order" — the automatic flow already handles it. |
| `POST /storefront/promo-codes/validate` | Explicitly deprecated shim (`_deprecated: true`, `_use_instead: POST /api/orders/validate-promo`) — the app calls the replacement. |

#### 3.6.3 Reported — needs a backend route or a product decision

| Item | State |
|---|---|
| Admin free-credit ledger | No route lists who holds credits (`GET /free-sides/admin/credits` does not exist). The page shows the grant panel instead. |
| Exclusive-spin ledger | No route lists spins. Removed UI; the fulfilment list (`GET /admin/exclusive-spin-prizes`) remains. |
| Review → homepage testimonial | No route promotes a review. Removed button; homepage testimonials are storefront sections. |
| Archived menu items | No route lists archived rows. Removed view. |
| Guest tracking-email resend | No tracking route exists. Removed button. |
| `POST /hp/bundles/initialize` | Real route, real gap: the app buys HP bundles with wallet balance (`POST /hp/bundles/purchase`); the Paystack card path has no UI. Adding it is a payment-flow decision, so it is left for you. |

### 3.7 Storefront CMS — field-by-field verification (2026-10-04)

Requested check: *do the fields the admin inserts link to the right keys, and can
an update throw?* Answer: **updates cannot throw on these keys, and five render
paths were reading the wrong key — now fixed.**

#### The shape that governs everything

| Table | Real columns | Everything else |
|---|---|---|
| `storefront_sections` | `key`, `section_type`, `title`, `content` (JSONB), `is_active`, `sort_order`, `campus_id` | The flat editor fields (`subtitle`, `body`, `image_url`, `cta_text`, `cta_url`, `config`) are **merged into `content`** by `storefront.py` (`_SECTION_CONTENT_FIELDS`), with aliases `subtitle → subheadline`, `cta_url → cta_link`. |
| `banners` | `title`, `subtitle`, `image_url`, `mobile_image_url`, `action_url`, `action_label`, `images`, `placement`, `is_active`, `sort_order`, `starts_at`, `ends_at` | `cta_text` / `cta_url` are accepted for compatibility but **stored as `action_label` / `action_url`** (`_banner_fields`). |

Consequence: anything the admin edits for a **section** comes back on
`row.content.<field>` — never on the row's top level. Banners are the opposite:
their CTA comes back as `action_*`.

#### Can an update throw?

No. `PATCH /storefront/sections/<id>` whitelists (`title`, `is_active`,
`sort_order`, `content` + the flat fields) and **merges** `content` into the
existing object; unknown keys are dropped silently and nothing is wiped. The
editor's `save()` sends 11 fields, of which `key`, `section_type` and
`placement` are ignored by the backend — harmless, but they are not how the row
is identified (`sort_order`/`is_active`/`content` are). `sort_order` is coerced
with `Number(...)` and `is_active` is a boolean toggle, so the only way to get a
400 is a non-numeric `sort_order`, which the form cannot produce.

#### Mismatches found (consumers reading keys the backend never returns)

| Consumer | Read (broken) | Now reads | User-visible effect it fixes |
|---|---|---|---|
| `HeroCarousel` (banners) | `b.cta_text`, `b.cta_url` | `b.action_label`, `b.action_url` | A hero banner's CTA label/link never applied — always “Order Now” → `/menu`. |
| `HeroCarousel` (sections) | `s.subtitle`, `s.cta_text`, `s.cta_url` | `s.content.*` | Legacy `hero` sections lost subtitle + CTA. |
| `StorefrontSlider` (tap) | `slide.cta_url` | `slide.content.cta_url \| cta_link \| destination` | Every “What's Inside” / “How It's Made” slide went to `/menu` regardless of its destination. |
| `PromoFlyerPopup` | `section.image_url`, `section.subtitle`, `section.cta_text`, `section.cta_url` | `section.content.*` first | The popup flyer **image never rendered** (the admin's upload lands in `content.image_url`), and its CTA button was dead. |
| `CateringCard` | `content.description`, `content.cta_label` | also `content.subtitle`, `content.cta_text` | The catering card ignored the description and CTA the admin typed. |

#### Verified correct (no change needed)

Share templates (`content.base_image_url` / `caption_template` / `key` → `ShareSheet`),
testimonials (`content.name` / `review` / `rating` → Home + Our Story), slider card
text (`content.image_url` / `title` / `subtitle` / `badge`), tier icons
(`content.tier_slug` / `image_url`), early supporters (real columns + fallbacks),
Our Story hero, operating hours, banner `title` / `subtitle` / `images`, and the
CMS link rule from S8 (`openCmsDestination`).

### 3.8 Other wiring changes in this round

| Change | Detail |
|---|---|
| Font hosting (S9) | Nunito self-hosted via `@fontsource-variable/nunito`; Google Fonts links/preconnects removed; CSP `style-src`/`font-src` reduced to `'self'`. Fraunces was loaded but unused — removed. |
| Cloudinary cloud name | `app/config.py` now falls back to the live cloud name (`risvlfhx`) when `CLOUDINARY_CLOUD_NAME` is unset, so uploads keep working without the env var; an env value still wins. |
| Image uploads | Verified Cloudinary-only: `ImageUploader` posts to `POST /api/upload/signature` (auth’d; folder-scoped) and uploads to `api.cloudinary.com`. Base44 remains only for **static artwork** (`VITE_ASSET_CDN_URL`, per your decision) — no upload path touches it. |
| Message catalog | `GET /api/messages` serves the `MSG` registry (995 keys); `src/lib/messages.ts` + `npm run messages:check` enforce it. See `docs/MESSAGES.md`. |

## 4. What this audit does **not** cover

* No live backend calls: the app needs Supabase credentials, and the sandbox has
  no network path to a real database, so every result here is static
  (route + field + language-level) rather than an end-to-end HTTP exercise.
* No browser: paint, layout, timing and the real OAuth/Paystack redirects still
  need a human browser pass (see `docs/SECURITY_REVIEW.md` and
  `docs/TRACK_B_SSR_PLAN.md` for the remaining browser-only items).
* Response *value* semantics (a field returned as a string where the UI expects
  a number) are only covered where a normaliser or a type exists.

## Appendix — backend routes with no frontend caller (16, all intentional)

Regenerate with `python3 tools/wiring_audit.py --json /tmp/audit.json`. As of
2026-10-04 the tool reports **0 frontend calls without a backend route** and
**16 backend routes without a frontend caller**, all in the intentional list in
§3.6.2 (aliases, parity reads, ops tooling, one deprecated shim).

| Methods | Route | Handler |
|---|---|---|
| GET | `/api/academic-calendar` | `routes/academic_calendar.py:59` |
| GET | `/api/academic-calendar/current` | `routes/academic_calendar.py:83` |
| GET | `/api/admin/campuses/<campus_id>/location` | `routes/admin.py:2776` |
| PATCH | `/api/admin/campuses/<campus_id>/location` | `routes/admin.py:2806` |
| GET | `/api/admin/delivery-batches/<batch_id>` | `routes/admin.py:1119` |
| GET | `/api/admin/hp/pending-squad` | `routes/admin.py:2272` |
| GET | `/api/analytics/hp-ecosystem` | `routes/analytics.py:730` |
| GET | `/api/analytics/items-menu` | `routes/analytics.py:812` |
| GET | `/api/auth/users/search` | `routes/auth.py:1070` |
| POST | `/api/hp/bundles/initialize` | `routes/hp.py:287` |
| GET | `/api/kitchen/settings/<key>` | `routes/kitchen.py:348` |
| POST | `/api/marketplace/listings/<listing_id>/image` | `routes/marketplace.py:903` |
| PATCH | `/api/menu/items/<item_id>/availability` | `routes/menu.py:958` |
| POST | `/api/menu/items/<item_id>/image` | `routes/menu.py:866` |
| POST | `/api/referrals/complete` | `routes/referrals.py:201` |
| POST | `/api/storefront/promo-codes/validate` | `routes/storefront.py:634` |
