# Field-contract audit — admin → API → backend → user

Date: 2026-10-04 · branch `arena/01a108db-holy-grills`
Scope: **field level**, not route level. "The endpoint exists" says nothing about whether a
field typed in the admin panel actually reaches the database and comes back out to a user.
Every row below was checked by reading the admin form's request payload, the backend
route's accepted-body list, and the column the value finally lands in.

---

## 1. The one real bug this found

### `POST /api/storefront/sections` silently dropped the image, subtitle and CTA

**Severity: high — it is the "storefront image" defect (item 6).**

`storefront_sections` stores everything visual in a **single JSONB `content` column**. There
is no `image_url`, `subtitle`, `cta_text` or `cta_url` column on the table.

- `PATCH /storefront/sections/<id>` already folded those flat body keys into `content`
  (via `_SECTION_CONTENT_FIELDS` / `_SECTION_CONTENT_ALIASES`). Editing a promo image worked.
- `POST /storefront/sections` did **not**. It only built `safe` from
  `key, title, section_type, content, is_active, sort_order`. Everything else in the body
  was discarded.

`AdminStorefront.create()` posts the flat shape:

```js
body.title = …; body.subtitle = …; body.image_url = …; body.cta_text = …; body.cta_url = …;
```

So **a newly created promo / popup / what's-inside / how-it's-made section saved only its
title**, with `content: {}`. It then rendered on the live homepage with no image and no
button — indistinguishable from "the upload button doesn't work" and from "the save didn't
take". Editing the same section afterwards *did* work, which is exactly why the bug looked
intermittent.

**Fix (backend, `app/routes/storefront.py`):** both routes now share one helper.

- `_section_content(data, base)` — folds `subtitle`, `body`, `image_url`, `cta_text`,
  `cta_url` (plus their legacy aliases `subheadline` / `cta_link`) and `placement` into
  `content`, merging over any explicit `content` object and over the row's existing
  `content`. Returns `None` for `content: null` so the caller still answers 400
  (D17-B13) rather than a `NOT NULL` 500.
- `_section_content_touched(data)` — keeps the existing "nothing to update" 400 behaviour
  on PATCH.

Create and update can no longer drift apart. Covered by
`holy-grills-backend/tests/test_storefront_section_fields.py` (8 new tests).

### `placement` on a section was a phantom field

`AdminStorefront` offered a **Placement** select (Home / Menu / Checkout) for promo and
popup sections. `storefront_sections` has **no `placement` column** — `placement` exists
only on `banners`. The backend ignored it, nothing on the public site reads a section
placement, so the control wrote to nowhere and the value was lost on reload.

**Fix:** the backend now persists it as `content.placement` on both create and update, and
`AdminStorefront` reads it back with `placementOf(s) = s.content?.placement ?? s.placement`.
No schema change, no dead control, and existing rows keep working.

---

## 2. Field-by-field matrix

Legend — **OK** value survives the round trip · **DROPPED** accepted by nobody, lost ·
**FOLDED** stored under a different name than the admin typed · **N/A** admin never sends it.

### Storefront sections (`/storefront/sections`) — editor: `AdminStorefront.tsx`

| Admin field | Sent as | Lands in | Before | After |
|---|---|---|---|---|
| Title | `title` | `storefront_sections.title` | OK | OK |
| Subtitle | `subtitle` | `content.subtitle` + `content.subheadline` | **DROPPED on create** | FOLDED |
| Image (uploader) | `image_url` | `content.image_url` | **DROPPED on create** | FOLDED |
| CTA label | `cta_text` | `content.cta_text` | **DROPPED on create** | FOLDED |
| CTA link | `cta_url` | `content.cta_url` + `content.cta_link` | **DROPPED on create** | FOLDED |
| Placement | `placement` | `content.placement` | **DROPPED (no column)** | FOLDED |
| Sort order | `sort_order` | `sort_order` | OK | OK |
| Active toggle | `is_active` | `is_active` | OK | OK |
| Key | `key` | `key` (create only — PATCH ignores it) | OK | OK |
| Testimonial name / review / rating | `content.*` | `content` | OK | OK |
| Share base image / caption / key | `content.base_image_url`, `content.caption_template`, `content.key` | `content` | OK | OK |
| Badge (slider tabs) | `content.badge` | `content` | OK | OK |

### Banners (`/storefront/banners`) — editors: `AdminBanners.tsx`, `AdminStorefront.tsx` (hero)

| Admin field | Sent as | Accepted by `_banner_fields()` | Verdict |
|---|---|---|---|
| Title / Image | `title`, `image_url` | yes (both required) | OK |
| Subtitle | `subtitle` | yes | OK |
| Desktop + mobile images | `image_url`, `mobile_image_url` | **yes on create and on edit** | OK — *earlier scan flagged this as missing; it was a false positive from reading the docstring instead of the code* |
| CTA label / link | `cta_text`, `cta_url` | yes → `action_label` / `action_url` | FOLDED |
| Placement | `placement` | yes | OK |
| Carousel images | `images[]` | yes | OK |
| Start / end | `starts_at`, `ends_at` | yes (create **and** edit) | OK |

### Newsletter campaigns (`/storefront/newsletter/campaigns`) — `AdminStorefront.tsx`

| Admin field | Sent as | Backend | Verdict |
|---|---|---|---|
| Subject / Message | `subject`, `body` | `_campaign_text()` — required, 200 / 20 000 char caps | OK |
| Send to every campus | `all_campuses: true` | `_campaign_target()` — super_admin only | OK (snake_case, not camelCase) |
| Campus | `campus_id` | super_admin only; campus admins forced to their own | OK |
| Test send | — | `/campaigns/test`, rate-limited 10/min | OK |

### Early supporters (`/storefront/early-supporters`) — `AdminStorefront.tsx`

Stored as `storefront_sections` rows with `section_type = 'early_supporter'`.

| Admin field | Sent as | Lands in | Verdict |
|---|---|---|---|
| Name | `name` | `title` + `content.name` | FOLDED |
| Photo | `photo_url` | `content.photo_url` | FOLDED |
| Social links / note | `social_links`, `note` | `content.*` | FOLDED |
| Sort order | `sort_order` | `sort_order` | OK |

### Uploads (`/upload/*`) — `ImageUploader.tsx`

| Step | Status |
|---|---|
| `POST /upload/signature` | OK — names the exact missing env vars and answers 503 with a `hint` when Cloudinary keys are absent |
| Paste-a-URL fallback | OK — always reachable, auto-opens on 503/501 |
| `GET /upload/status` | **was never called** — see §3 |

---

## 3. Item 7 — why every image upload "fails"

The backend already knows the answer; the UI just never asked.

`app/config.py` ships a hardcoded fallback cloud name (`CLOUDINARY_CLOUD_NAME` defaults to
`risvlfhx`) but **`CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET` have no fallback**. If
they are not set on the deployed service, then:

- `GET /api/upload/status` → `{"configured": false, "missing": ["CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]}`
- `POST /api/upload/signature` → 503 naming both variables, with a `hint` telling you to
  paste a URL instead.

`ImageUploader` only discovered that *after* you picked a file and the round trip failed —
so every image field looked like a broken button.

**Fix:** `ImageUploader` now calls `GET /upload/status` once on mount. When uploads are not
configured it opens the URL field immediately and shows a standing notice naming the exact
variables that are missing, instead of waiting for a failed upload.

**Action still required on your side (I cannot check this from here — the sandbox has no
outbound network):** set `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET` in the Render
backend environment and restart the service. Until then, paste image URLs.

---

## 4. Item 8 — WhatsApp was never missing; the settings *merge* was wrong

You were right: the backend already had it, end to end. The chain is

```
system_settings row (is_public = TRUE)
  → GET /api/storefront/config/public        [storefront.py get_public_config]
  → featureConfig.loadSystemSettings()       [settingsMap]
  → getStringSetting('whatsapp_support_number')
  → WhatsAppFloatingButton → https://wa.me/<number>
```

with `WHATSAPP_SUPPORT_NUMBER` / `WHATSAPP_SUPPORT_MESSAGE` as the server-env fallback when
the table has no row (D17-B22). `AdminSystemSettings.tsx` already carried
`whatsapp_support_number` and `whatsapp_support_enabled` in its `KNOWN_SETTINGS` map.

**The actual defect was in `featureConfig.loadSystemSettings()`.** It ran two passes, and
the second one clobbered the first:

```js
// pass 1 — public config: campus-scoped, is_public-filtered, campus row beats global row
settingsMap = { ...publicConfig };
// pass 2 — admin list, which overwrote it wholesale
(adminSettings || []).forEach((s) => { if (s && s.key) settingsMap[s.key] = s.value; });
```

`GET /admin/settings` is `SELECT * FROM system_settings ORDER BY key` — **every row, every
campus, `is_public = false` included, with no campus scoping at all**. So pass 2 had three
independent ways to hand an admin a value no user can ever receive:

1. **A private row overwrote the public one.** The public endpoint filters on
   `is_public = TRUE`; the admin list does not. Save a number, see it in the table, and the
   button still used the other one.
2. **Campus precedence was decided by row order.** With a global row *and* per-campus rows
   for the same key, the winner was whichever row the database happened to return last —
   not the campus-scoped row the backend itself would pick.
3. **A `null` value wiped a good value.** Pass 1 deliberately skips nulls; pass 2 did not.

That is precisely "the app opens a different number than any value in the settings table".
And it was never WhatsApp-specific — **it poisoned every one of the ~40+ settings keys.**

**Fix:** `src/lib/settingsMerge.ts` — a new import-free `mergeAdminSettings()` that applies
the backend's own precedence rules (drop other campuses' rows; with no campus selected keep
global rows only; campus row beats global row; nulls never overwrite) and **never replaces a
key the public config already resolved**. 14 unit tests in
`scripts/test-settings-merge.mjs`; wired into `npm run build` and the `frontend.yml` CI
workflow.

### Duplicates removed

You flagged this specifically, and you were right — I had built a second admin surface for
something that already existed:

- **Deleted** `src/components/admin/SupportChannelSettings.tsx` (and its two references in
  `AdminSystemSettings.tsx`). `AdminSystemSettings` already edits every one of those keys,
  with purpose text, boolean toggles and the `is_public` handling.
- **Deleted** `migrations/2026-10-04_seed_whatsapp_support_settings.sql` — it seeded rows
  the existing seed already covers.
- **Removed** the now-dead `normalizeWhatsAppNumber` re-export from
  `WhatsAppFloatingButton.tsx`.

The one genuine gap in the existing panel was `whatsapp_support_message`, which had no entry
in `KNOWN_SETTINGS`. **Added** — three lines in the panel that already existed, not a new
one.

### Still open, and it needs your call

`whatsapp_support_enabled` exists in **two** mechanisms: `system_settings` (read by the
floating button) and `feature_flags` (edited in `AdminFeatureFlags.tsx`, read by
`isFeatureEnabled`). `docs/SETTINGS.md` makes `system_settings` authoritative. I have not
retired the `feature_flags` copy because it changes live behaviour — say the word and I will.

---

## 5. Answer to "API client methods with no backend route — what does that imply?"

**It implies nothing, because there are none.** I re-ran the check properly this time.

The earlier "426 of 426 missing" figure was a bug in my own script: it compared frontend
paths like `/storefront/sections` (no prefix) against Flask rules that carry the blueprint's
`url_prefix` (`/api/storefront`). It reported every call as missing. Resolving the prefixes
from `app/__init__.py` gives:

| | |
|---|---|
| Distinct Flask `(method, rule)` pairs | **479** |
| `apiClient` calls in `liveApi.ts` | **426** |
| **Unmatched calls** | **0** |

The matcher is not trivially permissive — it rejects `/api/definitely/not/a/route`,
`/api/nope`, `/api/storefront/sections/1/extra` and `DELETE /api/menu/items/1`, while
accepting the real rules.

So what about the mocks?

- `src/lib/mockApi.ts` is four lines: `export { liveApi as mockApi } from './liveApi'`. The
  in-memory simulation is already retired; the name is now just an alias.
- `src/lib/storefrontMockData.ts` is 18 lines and calls `liveApi`.
- **Neither touches Supabase.** There is no shadow copy writing to your database behind the
  API's back — I checked both files line by line, and there is no second Supabase client.

Of the ~90 methods on `liveApi`, exactly two do not call `apiClient`, and neither is a mock:

- `getCheckinHistory()` — returns `[]` (no server-side feature yet).
- `downloadTicketPdf()` — uses `getToken()` + `localStorage` directly, because it streams a
  binary response the JSON client cannot parse. Legitimate.

**Conclusion: nothing to delete.** Every panel goes `admin → apiClient → your Flask API →
Supabase`. There is no parallel path to interfere with the intended one.

---

## 5b. Storefront image upload — already there, but wired to a field that never existed

You asked whether I added the upload UI or dropped it. **Neither — it was already there**,
in both places: the create modal (`AdminStorefront.tsx` "Image (required)") and the section
editor. Hero banners are covered too (`AdminBanners.tsx`: main image, mobile image, carousel
images).

But it was **broken in a way that made it look absent**. `storefront_sections` has no
top-level `image_url` — it lives in `content`. The editor read and wrote the flat names:

```js
<ImageUploader value={s.image_url || ''} onChange={(url) => upd(s.id, { image_url: url })} />
```

`GET /storefront/sections` returns raw rows, so `s.image_url` was **always `undefined`**.
The save worked (it folded into `content.image_url`), but the field rendered permanently
blank — upload an image, hit Save, and the uploader snapped back to empty. Same for
`subtitle`, `cta_text` and `cta_url`. That is the "there's no image upload / image URL is
required" report.

**Fix:** `sectionField(s, name)` reads `content[name]` → legacy alias → flat name;
`sectionPatch(s, name, value)` writes both so the value sticks on screen. `save()` sends
what the fields show.

| Field | Admin displayed | Backend stored | Verdict |
|---|---|---|---|
| `subtitle` | `s.subtitle` (**always blank**) | `content.subtitle` | fixed → `sectionField(s,'subtitle')` |
| `image_url` | `s.image_url` (**always blank**) | `content.image_url` | fixed → `sectionField(s,'image_url')` |
| `cta_text` / `cta_url` | `s.cta_*` (**always blank**) | `content.cta_*` | fixed |
| `title` | `s.title` | `title` (real column) | was already OK |
| testimonial / share fields | `s.content.*` | `content.*` | was already OK |

## 5c. System settings — campus admins could not save anything

Correct, and the UI did not reflect it. The backend rule
(`require_settings_write_permission` in `admin_gifts.py`) is:

- **global row** (`campus_id` NULL) → **super_admin only**
- **campus row** → super_admin, *or* that campus's own admin

`AdminSystemSettings` sent `PATCH /admin/settings/:key { value }` with **no `campus_id`**,
which meant:

- a **campus admin got a hard 403 on every save** — the panel was read-only for them;
- a **super admin** editing a campus-scoped row silently wrote the **global** row instead,
  or got 404 when no global row existed. So per-campus settings were uneditable by anyone.

Two more defects from the same root: `key={s.key}` collided when a key existed globally *and*
per campus, and `editKey === s.key` opened the editor on **every** campus copy at once.

**Fix:** rows are identified by `key:campus_id` (`rowId`); `save()`/`toggleBool()` take the
row and send its `campus_id`; global rows render a "Super admin only" badge instead of a Save
button that would answer 403.

## 5d. Delivery radius — it exists in the backend, but it had no screen

**Nowhere.** You were not missing it; there was no UI for it anywhere.

"Delivery range for my campus" is **two** values in **two** tables:

| Value | Stored in | Endpoint |
|---|---|---|
| Centre point (origin the radius is measured from) | `campuses.lat` / `campuses.lon` | `GET`/`PATCH /admin/campuses/<id>/location` |
| Radius in km | `kitchen_settings.max_delivery_radius_km` (per campus) | `GET`/`PATCH /kitchen/settings` |

Both had endpoints and no screen. `PATCH .../location` even accepts
`{ coordinates: "7.3021, 5.1391" }` pasted straight from Google Maps, and refuses points
outside Nigeria unless `force: true` — none of which was reachable.

**Added:** a **Delivery area** tab in **Admin → Delivery** (`AdminDeliveryArea.tsx`) with a
campus selector (super admin), a paste-from-Maps coordinate field, a radius field, an
"Open in Maps" link, and an explicit "save anyway" override for the outside-Nigeria
rejection. New `liveApi` methods `getCampusLocation` / `setCampusLocation`. 31 message keys
registered via `npm run messages:fix`.

Both values are what `GET /storefront/config/public` returns as `campus_lat`, `campus_lon`
and `max_delivery_radius_km`, and what `is_within_delivery_area` enforces at checkout — so
this is admin → API → user, wired end to end.

## 5e. Browser security headers — they existed, but CSP was report-only

The six headers were **already in `vercel.json`** — the scanner counts CSP as missing
because it was `Content-Security-Policy-Report-Only`, which blocks nothing.

Important: `vercel.json` is **generated** by `scripts/routes.mjs` (the same script behind
`npm run routes:check`), so the fix is one word in the generator, not a hand edit. That was
already the documented plan (`docs/SECURITY_REVIEW.md` §S4).

**Status: ENFORCED (2026-10-05).** It was briefly enforced, reverted, then re-enforced at
the owner's request: a report-only policy hides breakage in a console nobody reads, whereas
an enforced one makes a wrong allow-list entry obvious the moment the page loads. The
earlier "Failed to fetch" on login was CORS (the frontend origin was not in
`CORS_ORIGINS`), not CSP — that is now fixed separately.

- `scripts/routes.mjs` reads the inline script's SHA-256 **out of `index.html` at build
  time**, so the hash cannot drift from the file. Verified by hand: the served page's inline
  script hashes to `sha256-mxK/8VZ+…`, which is in the policy. (The other `<script>` in
  `index.html` is `type="application/ld+json"` — a data block, which CSP does not govern.)
- `npm run smoke` — **PASS**. It fetches every generated page from a local server that
  applies the same header rules Vercel will, and asserts: CSP enforced (not report-only), no
  duplicate report-only header, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS,
  CSP on the 404, and **all 9 inline script blocks across all 9 pages covered by the policy**.
- Static readiness scan of the source: **0 inline event handlers**, **0 `eval` /
  `new Function`**, no Google Fonts (`font-src 'self'` is correct), and **no direct Supabase
  access from the browser** (all Supabase traffic goes through the Flask API).

The four smoke assertions that were pinned to the old report-only name were updated to pin
the enforced state instead.

**Local development is never affected either way** — `vercel.json` is read by Vercel only,
never by the vite dev server.

**How to verify before it reaches production:** this branch gets its own Vercel **preview**
deployment. Load the preview, open DevTools, and check the console for CSP violations on
`/`, `/menu`, a paid checkout and the rider map. Only merge to `main` once it is clean.
If anything legitimately breaks, revert is one word in `scripts/routes.mjs` (rename the key
back to `Content-Security-Policy-Report-Only`) plus `npm run routes:sync`.

Two things I could **not** verify from here (no outbound network / no DB access):
- whether `VITE_API_BASE_URL` is set to something other than
  `https://holy-grills-backend.onrender.com` in the Vercel project — if it is, add that
  origin to `connect-src`;
- the live database schema (see §5f).

## 5f. Delivery radius and the database — yes, it needs checking

**I built against the existing row shape and added no new table or column.** The UI writes
exactly what the backend already consumed:

| Value | Write path | Row shape used |
|---|---|---|
| Centre point | `PATCH /admin/campuses/<id>/location` | `campuses.lat`, `campuses.lon`, `campuses.updated_at` |
| Radius | `PATCH /kitchen/settings` | `kitchen_settings` upsert on `key,campus_id`, with `value`, `updated_by`, `updated_at` |

**But I found a real alignment risk while checking.** `BACKEND_SOURCE_OF_TRUTH.md` documents

- `public.campuses` → `id, name, slug, is_active, created_at, updated_at` — **no `lat`, no `lon`**
- `public.kitchen_settings` → `key, value, updated_at, updated_by` — **no `campus_id`**

while the live code reads and writes all three. There is no checked-in schema (the two files
in `migrations/` are seeds), so I cannot resolve which is true from here. Most likely the
document is stale — the code comments describe *observed* live behaviour ("the anon/customer
client always read 0 rows here and every guest silently got the 15 km default"). But if the
columns really are missing, `set_campus_location` will 500 (it selects `lat,lon` outside a
try/except) and the radius upsert will fail on the `on_conflict="key,campus_id"`.

Added **`migrations/2026-10-05_delivery_area_columns.sql`**: fully idempotent, every
statement guarded, safe to run against a database that already has the columns. It starts
with a **VERIFY query** — run that in the Supabase SQL editor first; if it returns true for
all three, you do not need the rest. If not, it adds `campuses.lat/lon` with range
constraints, `kitchen_settings.campus_id`, the **unique index on `(key, campus_id)`** that
the PostgREST upsert requires, an `id` default, and seeds one `max_delivery_radius_km` row
per campus.

## 6. Corrections to earlier rounds

Three things I reported previously were wrong and are withdrawn:

1. **"POST /api/banners cannot set `mobile_image_url`"** — false. The route uses
   `_banner_fields()`, which accepts it on create and edit. My figure came from scanning the
   docstring, not the code.
2. **"Add a `SupportChannelSettings` panel and seed migration for WhatsApp"** — withdrawn.
   The backend already had it; the panel duplicated `AdminSystemSettings`. Both deleted (§4).
3. **"426 frontend API calls have no backend route"** — false, and it was a bug in my own
   script (§5). The correct number is zero.

---

## 7. Files changed in this round

| File | Change |
|---|---|
| `holy-grills-backend/app/routes/storefront.py` | `_section_content()` / `_section_content_touched()` helpers; `create_section` and `update_section` both fold flat fields into `content`; `placement` persisted as `content.placement`; create docstring documents the folded fields |
| `holy-grills-backend/app/messages.py` | 3 new `FE_IMAGE_UPLOADER_*` keys |
| `holy-grills-backend/tests/test_storefront_section_fields.py` | **new** — 8 tests pinning the create/update contract |
| `holy-grills-frontend/src/components/admin/AdminStorefront.tsx` | `placementOf()` reads placement from `content`; corrected the stale "backend accepts the full section row" comment |
| `holy-grills-frontend/src/components/admin/ImageUploader.tsx` | calls `GET /upload/status` on mount; opens the URL field and names the missing env vars when uploads are off |
| `holy-grills-frontend/src/lib/settingsMerge.ts` | **new** — `mergeAdminSettings()`, the fix for the WhatsApp/settings precedence bug |
| `holy-grills-frontend/scripts/test-settings-merge.mjs` | **new** — 14 tests, wired into `npm run build` + CI |
| `holy-grills-frontend/src/lib/featureConfig.ts` | `loadSystemSettings()` now merges admin rows through `mergeAdminSettings()` instead of clobbering |
| `holy-grills-frontend/src/components/admin/AdminSystemSettings.tsx` | added the missing `whatsapp_support_message` key; dropped the duplicate `SupportChannelSettings` panel |
| **deleted** `src/components/admin/SupportChannelSettings.tsx` | duplicated `AdminSystemSettings` |
| **deleted** `migrations/2026-10-04_seed_whatsapp_support_settings.sql` | seeded rows that already exist |
| `holy-grills-frontend/src/components/admin/AdminStorefront.tsx` | `sectionField()` / `sectionPatch()` — the section editor now reads and writes `content`, where the image actually lives |
| `holy-grills-frontend/src/components/admin/AdminSystemSettings.tsx` | sends the row's `campus_id` on PATCH so campus admins can save campus rows; `rowId()` keys; global rows gated to super admin |
| `holy-grills-frontend/src/components/admin/AdminDeliveryArea.tsx` | **new** — the missing delivery-radius screen (centre point + radius) |
| `holy-grills-frontend/src/components/admin/AdminDelivery.tsx` | new "Delivery area" tab |
| `holy-grills-frontend/src/lib/liveApi.ts` | `getCampusLocation()` / `setCampusLocation()` |
| `holy-grills-backend/app/messages.py` | 31 new `FE_ADMIN_DELIVERY_AREA_*` keys |
| `holy-grills-frontend/scripts/routes.mjs` | CSP flipped from report-only to **enforced** |
| `holy-grills-frontend/vercel.json` | regenerated (`npm run routes:sync`) — now serves `Content-Security-Policy` |
| `holy-grills-frontend/scripts/smoke.mjs` | assertions re-pinned to the enforced header |
| `holy-grills-backend/migrations/2026-10-05_delivery_area_columns.sql` | **new** — idempotent, guarded; verify query first |

## 8. Verification

```
# backend
/tmp/venv/bin/python -m pytest tests -q          # 46 passed (38 before + 8 new)

# frontend
npx tsc --noEmit                                 # clean
npx eslint src --quiet                           # clean
npm run messages:check                           # every call site resolves
npm run test:value-text                          # render-safety guards
npm run test:settings-merge                      # 14 passed — admin vs user value precedence
npm run build:client                             # builds
npm run smoke                                    # PASS — headers + every pre-rendered page
```

`npm run smoke` needs `npm run serve` running in another shell (it applies the same header
rules Vercel will, so the headers are tested rather than assumed).

Not verifiable from here: live Cloudinary credentials, whether a `whatsapp_support_number`
row exists with `is_public = true`, and campus-scoped data on the deployed service.
