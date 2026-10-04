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

## 4. Item 8 — WhatsApp is already implemented, and it is double-wired

There is no missing WhatsApp backend. Two mechanisms already exist for the same toggle:

| Mechanism | Where | Read by |
|---|---|---|
| `system_settings.whatsapp_support_number` / `whatsapp_support_enabled` | `BACKEND_SOURCE_OF_TRUTH.md` §14, consumer `app/routes/storefront.py` | public storefront config |
| `feature_flags.whatsapp_support_enabled` | `BACKEND_SOURCE_OF_TRUTH.md` §12, editor `AdminFeatureFlags.tsx` | `featureConfig.ts` |

`docs/SETTINGS.md` already states the intended rule: **`system_settings` is authoritative**
(per-campus → global → env, env being the fallback and never the only copy). The
`feature_flags` row is a second, independent switch — `AdminFeatureFlags.tsx` even ships an
on-screen note that DB flags and the app's built-in client toggles are separate mechanisms.

That duplication is the most likely reason a number other than the one in your settings
table opens in the app. **Recommended direction: keep `system_settings`, retire the
`feature_flags` copy** — but I have not made that change yet, because it changes behaviour
on the live site and needs your call (see §6).

---

## 5. Answer to "frontend files with no backend route — are any of them mocks?"

Checked directly, and **no**: there is no mock or shadow-Supabase layer in the frontend API
client.

- `src/lib/mockApi.ts` is four lines: `export { liveApi as mockApi } from './liveApi'`.
  The in-memory simulation is already retired; the name is now just an alias. Nothing was
  deleted because nothing duplicative remains.
- `src/lib/storefrontMockData.ts` is 18 lines and calls `liveApi` — backend-only, no fallback.
- Neither file touches Supabase. Every admin panel goes through `apiClient` → your Flask API.

Of the ~90 methods on `liveApi`, exactly two do not call `apiClient`, and neither is a mock:

- `getCheckinHistory()` — returns `[]` (feature not built server-side yet).
- `downloadTicketPdf()` — uses `getToken()` + `localStorage` directly, because it streams a
  binary response that the JSON client cannot parse. Legitimate.

So the "no matching backend route" entries are **frontend calls ahead of the backend**, not
duplicate implementations. They fail loudly against the API rather than quietly writing to
the wrong place.

---

## 6. Corrections to the previous round

Two things I reported earlier were wrong and are withdrawn:

1. **"POST /api/banners cannot set `mobile_image_url`"** — false. The route uses
   `_banner_fields()`, which accepts it on both create and edit. My earlier figure came from
   scanning the docstring, not the code.
2. **"Add a `SupportChannelSettings` panel / seed migration for WhatsApp"** — withdrawn as a
   proposal. The backend already has it. The new panel and
   `migrations/2026-10-04_seed_whatsapp_support_settings.sql` are **not yet deleted** — they
   are the wrong shape for the fix and I want your confirmation before removing them, since
   §4 has two defensible resolutions (retire the `feature_flags` copy, or retire the
   `system_settings` copy).

---

## 7. Files changed in this round

| File | Change |
|---|---|
| `holy-grills-backend/app/routes/storefront.py` | `_section_content()` / `_section_content_touched()` helpers; `create_section` and `update_section` both fold flat fields into `content`; `placement` persisted as `content.placement`; create docstring documents the folded fields |
| `holy-grills-backend/app/messages.py` | 3 new `FE_IMAGE_UPLOADER_*` keys |
| `holy-grills-backend/tests/test_storefront_section_fields.py` | **new** — 8 tests pinning the create/update contract |
| `holy-grills-frontend/src/components/admin/AdminStorefront.tsx` | `placementOf()` reads placement from `content`; corrected the stale "backend accepts the full section row" comment |
| `holy-grills-frontend/src/components/admin/ImageUploader.tsx` | calls `GET /upload/status` on mount; opens the URL field and names the missing env vars when uploads are off |

## 8. Verification

```
# backend
/tmp/venv/bin/python -m pytest tests -q          # 46 passed (38 before + 8 new)

# frontend
npx tsc --noEmit                                 # clean
npx eslint src --quiet                           # clean
npm run messages:check                           # every call site resolves
```

Not verifiable from here: live Cloudinary credentials, whether a `whatsapp_support_number`
row exists with `is_public = true`, and campus-scoped data on the deployed service.
