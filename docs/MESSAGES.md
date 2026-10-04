# Message catalog — one place for every user-facing string

**Status:** mechanism shipped, reference slice migrated (26 strings).
**Owner files:** `holy-grills-backend/app/messages.py` (copy) ·
`holy-grills-backend/app/routes/messages.py` (serving) ·
`holy-grills-frontend/src/lib/messages.ts` (client) ·
`holy-grills-frontend/scripts/messages-check.mjs` (guard).

## Why

The backend already kept **every user-facing string in one file** (`MSG`, ~1000
constants) and returned them in API bodies. The frontend authored its own copy
separately — 404 hardcoded message literals across 92 files — so a wording
revamp meant editing TypeScript too. This closes that gap: the client now renders
backend copy for its own messages as well.

## Contract

```
GET /api/messages → 200 {"messages": {"FE_CHECKOUT_SELECT_HOSTEL": "Please select your hostel", …}, "count": 995}
```

* Public, no auth (it is copy, not data), `Cache-Control: public, max-age=300`.
* `{currency}` / `{platform}` placeholders are resolved server-side from the
  environment via `resolve_msg`, so currency wording follows the deployment.

## Frontend usage

```ts
import { t } from '@/lib/messages';

setError(t('FE_CHECKOUT_SELECT_HOSTEL', 'Please select your hostel'));
toast({ title: t('FE_CART_SAVED_TITLE', '❤️ Saved to your favourites'),
        description: t('FE_CART_SAVED_BODY', '{item} moved to Saved Items.', { item: name }) });
```

Rules
* **Key** — `FE_*` for frontend-owned copy; other keys are API/notification
  messages the client normally receives in response bodies.
* **Fallback** — the string that ships in the bundle. It renders until the
  catalog lands, if the request fails (offline, older deploy), or if the key is
  missing. The UI never renders a raw key and never blocks on the fetch.
* **Placeholders** — `{name}` style, filled from the third argument; the same
  placeholder syntax the backend uses, so a string can move between the two.
* **Static copy in JSX** — components that render catalog copy directly (not at
  event time) call `useMessages()` so they re-render when the catalog arrives.
  Handlers that build a string when the user acts can call `t()` directly.
* **The catalog warms once per page load** — `void loadMessages()` in
  `main.tsx`, fire-and-forget.

## The guard

`npm run messages:check` (part of `npm run build`):

| Result | Meaning |
|---|---|
| **FAIL** | a `t('FE_…')` call site whose key the registry does not define — the copy could never be reworded from the backend |
| WARN (drift) | the bundled fallback no longer matches the registry text (registry wins; clean up when convenient) |
| note | `FE_` keys in the registry with no call site yet |

It skips with a note when the backend checkout is not next to the frontend.

## Rewording copy

1. Edit the string in `holy-grills-backend/app/messages.py`.
2. Deploy the backend. Every surface — API responses **and** frontend
   toasts/validation — changes together. Nothing to touch on the client.
3. Optionally refresh the frontend fallback in the same pass (keeps offline
   rendering in sync with the new wording; `messages:check` prints the list).

## Migrated so far (26 strings)

| File | Strings | What moved |
|---|---|---|
| `pages/Checkout.tsx` | 11 | delivery/hostel/gate/name/phone/email validation, split-payment errors, free-side added/failed toasts |
| `pages/Cart.tsx` | 4 | sign-in-to-save, saved, save failed, moved-back toasts |
| `pages/Login.tsx` | 2 | welcome-back toast, login-failed fallback |
| `pages/Register.tsx` | 1 | signup success toast |
| `pages/ResetPassword.tsx` | 2 | password-mismatch, reset-failed fallback |

## Remaining work (403 literals in 92 files)

Mechanical, file by file — each string becomes `t('FE_<FILE>_<WHAT>', '<same text>')`
plus a line in the registry. Highest-volume files first:

| File | Literals |
|---|---|
| `components/admin/AdminStorefront.tsx` | 25 |
| `components/admin/AdminEvents.tsx` | 20 |
| `components/admin/AdminMenu.tsx` | 14 |
| `components/admin/AdminExclusiveSpin.tsx` | 14 |
| `components/admin/AdminUsers.tsx` | 13 |
| `components/admin/AdminFreeCredits.tsx` | 13 |
| `components/admin/AdminDelivery.tsx` | 13 |
| `components/admin/AdminBanners.tsx` | 12 |
| `pages/OrderLocks.tsx` | 11 |
| `hooks/useRiderData.ts` | 10 |

Recount any time with:

```bash
cd holy-grills-frontend/src && grep -ro "toast({ title: ['\"]\|setError(['\"]\|throw new Error(['\"]" \
  --include=*.tsx --include=*.ts . | wc -l
```

**Not in scope:** UI labels, headings and empty-state prose that are part of the
layout (they are design copy, not messages). Dynamic `e.message` toasts already
carry backend text and need no change.
