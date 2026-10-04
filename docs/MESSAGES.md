# Message catalog — one place for every user-facing string

**Status:** mechanism shipped and the bulk of the copy migrated — **477 call
sites / 443 registry keys** across 98 files. 70 interpolated strings
(`${…}`) remain, listed at the end.
**Owner files:** `holy-grills-backend/app/messages.py` (copy) ·
`holy-grills-backend/app/routes/messages.py` (serving) ·
`holy-grills-frontend/src/lib/messages.ts` (client) ·
`holy-grills-frontend/scripts/messages-check.mjs` (guard) ·
`holy-grills-frontend/scripts/messages-codemod.mjs` (bulk migration).

## Why

The backend already kept **every user-facing string in one file** (`MSG`,
~1,400 constants) and returned them in API bodies. The frontend authored its own
copy separately — ~400 hardcoded message literals across 92 files — so a wording
revamp meant editing TypeScript too. This closes that gap: the client now renders
backend copy for its own messages as well.

## Contract

```
GET /api/messages              → 200 {"messages": {…1,413 keys…}, "count": 1413}
GET /api/messages?prefix=FE_   → 200 {"messages": {…443 keys…},  "count": 443}
```

* Public, no auth (it is copy, not data), `Cache-Control: public, max-age=300`.
* `{currency}` / `{platform}` placeholders are resolved server-side from the
  environment, so currency wording follows the deployment.
* `?prefix=` narrows the catalog to a key prefix (validated against
  `[A-Z][A-Z0-9_]{0,24}`; anything else is a 400). The frontend asks for `FE_`
  alone — 30 KB instead of 95 KB — because the other keys are text the client
  receives inside API response bodies. The unfiltered catalog stays available.

## Frontend usage

```ts
import { msg } from '@/lib/messages';

setError(msg('FE_CHECKOUT_SELECT_HOSTEL', 'Please select your hostel'));
toast({ title: msg('FE_CART_SAVED_TITLE', '❤️ Saved to your favourites'),
        description: msg('FE_CART_SAVED_BODY', '{item} moved to Saved Items.', { item: name }) });
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
  Handlers that build a string when the user acts can call `msg()` directly.
* **The catalog warms once per page load** — `void loadMessages()` in
  `main.tsx`, fire-and-forget.
* **The helper is called `msg`, not `t`** — `t` is already a timer/type variable
  in ~78 files of this codebase, so a one-letter helper would have been shadowed
  in exactly the places that need it.

## The guard

`npm run messages:check` (part of `npm run build`):

| Result | Meaning |
|---|---|
| **FAIL** | a `msg('FE_…')` call site whose key the registry does not define — the copy could never be reworded from the backend |
| WARN (drift) | the bundled fallback no longer matches the registry text (registry wins; clean up when convenient) |
| note | `FE_` keys in the registry with no call site yet |

It skips with a note when the backend checkout is not next to the frontend.

## Bulk migration (`scripts/messages-codemod.mjs`)

```bash
node scripts/messages-codemod.mjs --dry                 # report only
node scripts/messages-codemod.mjs --write --manifest /tmp/keys.json
```

It rewrites exactly three shapes, and only when the message is a **plain**
string literal:

| Shape | Becomes |
|---|---|
| `toast({ title: 'X', description: 'Y' })` | `toast({ title: msg('FE_…', 'X'), description: msg('FE_…', 'Y') })` |
| `setError('X')` | `setError(msg('FE_…', 'X'))` |
| `throw new Error('X')` | `throw new Error(msg('FE_…', 'X'))` |

* `toast(…)` bodies are located with a string/comment-aware scanner, so nested
  objects, JSX and `)` inside strings cannot confuse it. `title:` keys **outside**
  a toast call (page metadata, legal copy, list rows) are deliberately left
  alone — that is content, not messages.
* Keys are derived from the file and a slug of the text
  (`AdminBanners.tsx` + "Save failed" → `FE_ADMIN_BANNERS_SAVE_FAILED`);
  identical text in one file shares a key, `_2` disambiguates a collision.
* The fallback written into the call is the original literal, byte for byte, and
  the registry gets the **rendered** text (`can\'t` → `can't`), so nothing is
  paraphrased and `messages:check` can compare the two.
* A file that binds `msg` itself is skipped and reported (they were renamed
  inline so the sweep could finish).

`--manifest` writes the generated key → text → file map, which is what the
backend append consumes; the 417-key block in `app/messages.py` was produced
from one such run.

## Rewording copy

1. Edit the string in `holy-grills-backend/app/messages.py`.
2. Deploy the backend. Every surface — API responses **and** frontend
   toasts/validation — changes together. Nothing to touch on the client.
3. Optionally refresh the frontend fallback in the same pass (keeps offline
   rendering in sync with the new wording; `messages:check` prints the list).

## Migrated

| Slice | Sites | Keys | What moved |
|---|---|---|---|
| First, by hand | 26 | 26 | checkout validation + free-side, cart, login, register, reset-password |
| Bulk, by codemod | 451 | 417 | every plain-literal toast/setError/throw across 93 files — admin screens first, then pages, hooks and components |
| **Total** | **477** | **443** | 98 files converted; lint, typecheck and `messages:check` enforce it on every build |

## Remaining work — 70 interpolated strings in 34 files

These need a human: an interpolated message must be split into registry text plus
**named** placeholders (`You sent {amount} HP`), which is a wording decision, not
a mechanical one.

| Shape | Count |
|---|---|
| `toast({ title/description: \`… ${x} …\` })` | 69 |
| `setError(\`… ${x} …\`)` | 1 |
| `throw new Error(\`… ${x} …\`)` | 0 |

Recount any time with:

```bash
cd holy-grills-frontend && node scripts/messages-codemod.mjs --dry
```
