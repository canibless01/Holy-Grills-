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

## 1. Route level — 421 of 427 frontend calls resolve

**Six frontend calls have no backend route.** All six are already labelled
in-code (`// F5 GAP:`), all six degrade to an empty state rather than breaking a
page, and none is on the checkout path:

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

## 4. What this audit does **not** cover

* No live backend calls: the app needs Supabase credentials, and the sandbox has
  no network path to a real database, so every result here is static
  (route + field + language-level) rather than an end-to-end HTTP exercise.
* No browser: paint, layout, timing and the real OAuth/Paystack redirects still
  need a human browser pass (see `docs/SECURITY_REVIEW.md` and
  `docs/TRACK_B_SSR_PLAN.md` for the remaining browser-only items).
* Response *value* semantics (a field returned as a string where the UI expects
  a number) are only covered where a normaliser or a type exists.

## Appendix — backend routes with no frontend caller (34)

| Methods | Route | Handler |
|---|---|---|
| GET | `/api/academic-calendar` | `routes/academic_calendar.py:59` |
| GET | `/api/academic-calendar/current` | `routes/academic_calendar.py:83` |
| GET | `/api/admin/campuses/<campus_id>/location` | `routes/admin.py:2776` |
| PATCH | `/api/admin/campuses/<campus_id>/location` | `routes/admin.py:2806` |
| GET | `/api/admin/delivery-batches/<batch_id>` | `routes/admin.py:1119` |
| POST | `/api/admin/departments/<dept_id>/restore` | `routes/departments.py:374` |
| POST | `/api/admin/exclusive-spin-grant` | `routes/admin.py:2470` |
| GET | `/api/admin/hp/pending-squad` | `routes/admin.py:2272` |
| GET | `/api/analytics/hp-ecosystem` | `routes/analytics.py:730` |
| GET | `/api/analytics/items-menu` | `routes/analytics.py:812` |
| GET | `/api/auth/users/search` | `routes/auth.py:1070` |
| POST | `/api/challenges/push-subscribed` | `routes/challenges.py:259` |
| GET | `/api/departments/<dept_id>` | `routes/departments.py:138` |
| GET | `/api/departments/faculties` | `routes/departments.py:105` |
| POST | `/api/free-sides/admin/credits` | `routes/free_sides.py:130` |
| GET | `/api/free-sides/admin/items` | `routes/free_sides.py:72` |
| POST | `/api/free-sides/admin/items` | `routes/free_sides.py:96` |
| DELETE | `/api/free-sides/admin/items/<item_id>` | `routes/free_sides.py:266` |
| PATCH | `/api/free-sides/admin/items/<item_id>` | `routes/free_sides.py:232` |
| POST | `/api/free-sides/select` | `routes/free_sides.py:299` |
| DELETE | `/api/free-sides/select/<selection_id>` | `routes/free_sides.py:347` |
| POST | `/api/hp/bundles/initialize` | `routes/hp.py:287` |
| GET | `/api/kitchen/settings/<key>` | `routes/kitchen.py:348` |
| POST | `/api/marketplace/listings/<listing_id>/image` | `routes/marketplace.py:903` |
| PATCH | `/api/menu/items/<item_id>/availability` | `routes/menu.py:958` |
| POST | `/api/menu/items/<item_id>/image` | `routes/menu.py:866` |
| PATCH | `/api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>` | `routes/menu.py:1246` |
| POST | `/api/referrals/complete` | `routes/referrals.py:201` |
| GET | `/api/storefront/newsletter/campaigns` | `routes/storefront.py:1311` |
| POST | `/api/storefront/newsletter/campaigns` | `routes/storefront.py:1263` |
| GET | `/api/storefront/newsletter/campaigns/<campaign_id>` | `routes/storefront.py:1326` |
| POST | `/api/storefront/newsletter/campaigns/<campaign_id>/cancel` | `routes/storefront.py:1337` |
| POST | `/api/storefront/newsletter/campaigns/test` | `routes/storefront.py:1354` |
| POST | `/api/storefront/promo-codes/validate` | `routes/storefront.py:634` |
