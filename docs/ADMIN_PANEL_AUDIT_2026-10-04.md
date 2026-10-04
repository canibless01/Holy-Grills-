# Admin panel audit & fixes — 2026-10-04

A pass over the seven reported admin/auth problems, plus the sweep that followed
them. Every entry states **what was wrong**, **why**, and **where it is fixed**.

| # | Reported | Root cause | Status |
|---|----------|-----------|--------|
| 1 | User Management crashes when a user is opened | Rendered an object as a React child | Fixed + regression test |
| 2 | "Remember me" forgets everything | Only a flag was stored; no identity, no real form submit | Fixed |
| 3 | Campus selector doesn't change the data | **No backend route ever read `X-Campus-ID`** | Fixed |
| 4 | Analytics → Brand Partnerships text breaks the page margin | Flex item can't shrink below min-content | Fixed + CSS guard |
| 5 | System Settings long values break the page margin | Same flex/min-content issue | Fixed + CSS guard |
| 6 | No image upload for storefront hero/banner | Create form had no image field; list hid inactive rows | Fixed |
| 7 | All image uploads fail | Cloudinary env vars unset, error hidden behind a generic toast | Diagnosed, surfaced, fallback added |
| 8 | WhatsApp settings — several rows, none of them used | Keys never seeded; new rows created private; `getSetting()` turned the number into `NaN` | Fixed + migration + panel |

---

## 1. User Management — crash on open

**Symptom.** The user list renders (HP + wallet are visible). Clicking a user
opens the drawer, which immediately dies.

**Cause.** `GET /admin/users/:id/hp` returns `hp_balance` from
`app/services/hp_service.get_hp_balance()`, and that dict embeds the tier twice:

```python
# hp_service.get_hp_balance()
{"tier": {"tier": {<hp_tiers row>}, "is_in_grace_period": False}, …}
```

`liveApi.getUserHp()` drilled into `hp_balance` for the numbers but copied
`tier` across verbatim, so `hp.tier` was a *container*, not a name.
`AdminUsers.tierLabel()` then did `u.tier.name || u.tier.tier` — and
`u.tier.tier` is the **row object**. Rendering it throws
`Objects are not valid as a React child`, which propagates out of the drawer and
takes the whole Users section down (HP is the tab that opens by default, so it
fired on every open).

Two related mis-mappings were in the same function and are fixed too:

* `total` — the backend calls the combined figure `total_visible`, so the HP
  tile always read `0`.
* `tier_multiplier` — the backend calls it `tier_bonus_multiplier`, so the earn
  rate never showed.

**Fix.**

* `src/lib/valueText.ts` (new, import-free) — `hpTierName()` walks up to four
  levels and always returns a string or `null`; `safeText()` is the generic
  "this should be a word" coercion; `normalizeWhatsAppNumber()` is shared with
  the chat button.
* `src/lib/liveApi.ts` — `getUserHp()` maps `total_visible`,
  `tier_bonus_multiplier`, `hp_earned_120day` and `degraded`, and flattens the
  tier through `hpTierName()`.
* `src/components/admin/AdminUsers.tsx` — `tierLabel()` / `txt()` now go through
  the shared helpers, and the drawer shows a "some HP figures could not be read"
  note when the backend reports `degraded`.
* `scripts/test-value-text.mjs` + `npm run test:value-text` (wired into
  `npm run build` and CI) — 27 assertions, including the exact crash shape and a
  self-referential payload.
* `AdminCatering` / `AdminEvents` render `r.tier` through `safeText()` too —
  same class of bug, one line each.

## 2. "Remember me"

**Cause.** The checkbox wrote a single flag (`hg_remember`) that only chose
*where the JWT is stored* (local vs session). Nothing remembered the identity,
and the auto-kickstart path called `doLogin()` directly instead of submitting
the form, so Chrome/Safari never saw a sign-in and never offered to save the
password.

**Fix** (`src/pages/Login.tsx`, `src/pages/ForgotPassword.tsx`):

* The email is persisted (`hg_remember_email`) and pre-fills the field on the
  next visit — and on the Forgot-password screen.
* Fields now carry `name="email"` / `name="password"` and
  `autoComplete="username"` / `autoComplete="current-password"`, which is what
  the browser's password manager keys on.
* The auto-kickstart uses `formRef.current.requestSubmit()` instead of calling
  the handler directly, so an autofilled sign-in is a *real* form submission and
  the browser offers to remember the password.
* `handleSubmit` reads the DOM values as a fallback, because autofill fills an
  input without firing React's `onChange`.
* Unchecking the box forgets the stored email immediately.

**Deliberate omission:** the password itself is *not* written to localStorage.
It would be readable by any script on the page. The pre-fill you're describing
is the browser's own password manager, and it now works.

## 3. Campus selector — "I pick a campus and nothing changes"

**Cause.** This was not a frontend wiring bug. The selector wrote
`hg_admin_campus_id` and `apiClient` sent it as `X-Campus-ID` — but **no route in
the backend ever read that header**. `resolve_scoped_campus_id()` only looked at
the `campus_id` query parameter, and for a super-admin with no parameter it
returned `None` (all campuses) every time. The switcher was, in effect,
decorative.

**Fix.**

* `app/middleware/auth.py` — new `header_campus_id()` (validated, returns `None`
  for junk), and `resolve_scoped_campus_id()` now falls back to it for
  `super_admin`. That single function is how ~60 admin list/writer routes resolve
  scope, so every panel follows the selector at once.
* `app/utils/campus_scope.py` (`resolve_write_campus`) and
  `app/routes/storefront.py` (`_write_campus_id`) honour the header too, so a
  banner created while "Futa" is selected belongs to Futa.
* `src/pages/Admin.tsx` — the content region is keyed on the selected campus, so
  switching remounts the section and re-fetches with the new header (each panel
  loads once on mount).
* `src/lib/apiClient.ts` + `src/lib/campusContext.tsx` — a super-admin who picks
  "All Campuses" (or never touches the switcher) now sends **no** campus header.
  Previously their own profile campus was sent, which would have scoped them to
  one campus behind a header that read "All Campuses". Recorded explicitly as
  `hg_admin_scope_all`.

## 4–5. Text overflowing the page margin

**Cause.** A flex item's automatic minimum size is its *min-content* width, and
`overflow-wrap: break-word` does **not** reduce min-content. So a long value
(a JSON blob, a URL, a contact email) inside a `.flex` row pushes the row — and
the page — wider than the viewport, and neither `truncate` nor `break-words`
stops it. That is why it broke on mobile *and* desktop.

**Fix.**

* `src/index.css` — scoped to `.admin-scope`, `min-width: 0` is applied to flex
  children that already asked to be clipped or wrapped (`.truncate`,
  `.break-words`, `.flex-1`). `min-width: 0` unlocks the shrink; only then does
  the ellipsis or the wrap actually happen. This is the guard for the ~40 other
  admin rows with the same shape.
* `AdminAnalytics.tsx` — the Brand Partnerships row is now `min-w-0 flex-1` with
  `break-words`, stacks on mobile, and its buttons are `shrink-0`. An
  unparseable `created_at` no longer renders "Invalid Date".
* `AdminSystemSettings.tsx` — the key/value rows are `min-w-0`; the description
  and value wrap.

## 6. Storefront hero / banner — "there's no image upload"

**Cause.** Two separate gaps:

* The Hero and Banners tabs render `AdminBanners`, whose **create** modal had no
  image field at all — and `POST /storefront/banners` requires both `title` and
  `image_url`, so creating a banner failed with a field-required error and the
  only uploader on the page lived on a banner you could not create.
* `GET /storefront/banners` returns `is_active = true` rows only, so an
  inactive banner (or a brand-new one that failed creation) simply vanished from
  the panel.

**Fix.**

* `AdminBanners.tsx` — the create modal now has a required **Main image**
  uploader; each banner card has an editable main image, a new **Mobile image**
  (the `mobile_image_url` column existed but had no UI), and the carousel
  uploader it already had. Inactive banners are shown with an `INACTIVE` pill.
* `app/routes/storefront.py` — `GET /storefront/banners` and
  `GET /storefront/sections` accept `include_inactive=1` **for admin callers
  only**; public callers still get the active set. `liveApi` sends it from the
  admin methods.

## 7. Image uploads failing

**Cause.** `POST /api/upload/signature` returns `503 UPLOAD_NOT_CONFIGURED`
unless `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and
`CLOUDINARY_API_SECRET` are all set on the server. `CLOUDINARY_CLOUD_NAME`
defaults to the live account (`risvlfhx`); the key and secret have **no default**,
so with those two unset every upload fails — and the frontend replaced the real
error with "Upload failed. Please try again.", which reads like a broken button.

I cannot read your Render environment from here, so verify with the new endpoint:

```
GET /api/upload/status      (authenticated)
→ {"configured": false, "missing": ["CLOUDINARY_API_KEY","CLOUDINARY_API_SECRET"], "cloud_name": "risvlfhx"}
```

**Fix.**

* `app/routes/uploads.py` — the 503 now names the exact missing variables and
  carries a `hint`; new `GET /upload/status` reports the same thing without
  attempting an upload.
* `ImageUploader.tsx` — surfaces the server's message *and* its hint instead of
  the generic toast, and Cloudinary's own error text when the direct POST fails.
* **Paste-an-image-URL fallback** on every image field (always available,
  auto-revealed on a 503). This is what unblocks the "image URL is required"
  dead end: you can now fill any image field even while Cloudinary is
  unconfigured, and it works for every create form that requires an image.

## 8. WhatsApp — several rows, none of them used

**The chain, end to end** (now documented in the component):

```
system_settings row (is_public = TRUE)
  → GET /api/storefront/config/public     ← the ONLY settings source a visitor has
  → featureConfig.loadSystemSettings()
  → WhatsAppFloatingButton → https://wa.me/<number>
```

**Three things broke it, and all three looked like "it isn't reading the table":**

1. **No rows existed.** `migrations/2026-10-04_seed_system_settings.sql` seeds
   40 keys and `whatsapp_support_number` / `_enabled` / `_message` are not among
   them, so the button always fell back to the hardcoded `2348000000000`.
2. **Rows created from the admin screen were private.** `POST /admin/settings`
   never set `is_public`, so it took the column default (`false`) — and
   `GET /storefront/config/public` filters on `is_public`. The number was saved,
   listed for admins, and never served. Seeing "several" rows is normal
   (global + one per campus); the new scope badge says which is which.
3. **`getSetting()` coerced numeric-looking strings.** `"+234 801 234 5678"`
   became `NaN`, and the link became `https://wa.me/NaN`.

**Fix.**

* `migrations/2026-10-04_seed_whatsapp_support_settings.sql` (new) — seeds the
  three keys as **public**, idempotently, and publicises existing rows for those
  three keys (the value is never touched). The number is displayed to every
  visitor by design, so it cannot meaningfully be private.
* `app/routes/admin_gifts.py` — `POST /admin/settings` creates rows with
  `is_public = true` by default (with a fallback if the column is absent), and
  `PATCH /admin/settings/<key>` accepts `is_public`.
* `src/components/admin/SupportChannelSettings.tsx` (new) — a **Support &
  WhatsApp** card at the top of System Settings: each key with its scope
  (All campuses / campus name / "viewing now"), a Public/Private toggle, inline
  editing, a live preview of the `wa.me/` link, and a "Create (public)" button
  for a missing key.
* `src/lib/featureConfig.ts` — `getStringSetting()` (no numeric coercion) and
  `getBoolSetting()` (so the string `"false"` can actually turn the button off).
* `WhatsAppFloatingButton.tsx` — reads strings, normalises the number, and hides
  itself rather than link to `wa.me/NaN`.
* `app/routes/storefront.py` + `.env.example` — `WHATSAPP_SUPPORT_NUMBER` and
  `WHATSAPP_SUPPORT_MESSAGE` env fallbacks, documented with the precedence
  (campus row → global row → env → built-in default).

---

## The wider sweep

* **Every frontend API call has a backend route.** Mechanical check of all 426
  `apiClient.*` call sites in `liveApi.ts` against the Flask URL map: **0
  missing**. (Script used: `match apiClient paths vs app.url_map`.)
* **Every sidebar section renders.** All 32 entries in `adminSections.ts` have a
  `case` in `Admin.tsx` and a title.
* **Image fields.** Menu items, rewards, events, free sides, marketplace
  listings, tier icons, early supporters, share templates and CMS sections
  already had uploaders; the gaps found (banner create, banner mobile image) are
  fixed above. All of them now also accept a URL.
* **Invisible-rows bug class.** Found and fixed for banners and CMS sections
  (see #6); the same pattern is worth watching for on other admin lists.
* **Joined rows rendered directly.** Checked every embedded Supabase select
  (`profiles`, `hp_tiers`, `menu_categories`, `order_items`, …) against its
  consumer; the two that rendered a possibly-object value (`AdminCatering`,
  `AdminEvents`) now go through `safeText()`.

## Verification

```
frontend:  npm run typecheck · npm run lint · npm run test:value-text
           npm run routes:check · npm run messages:check · npm run build:client
backend:   pytest tests -q            → 38 passed
           header_campus_id / resolve_scoped_campus_id exercised against a
           real request context (super-admin, junk header, non-super-admin)
```

Not verified here (needs your deployed environment): the live Cloudinary
credentials, and the seeded WhatsApp rows — run the migration, then check
`GET /api/storefront/config/public` contains `whatsapp_support_number`.
