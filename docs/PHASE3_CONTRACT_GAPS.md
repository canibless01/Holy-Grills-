# PHASE 3 — CONTRACT GAPS (logged, not fixed)

Decision (user, 2026-10-04): **the backend is the source of truth**; the frontend aligns to it.
No new UIs and no new backend endpoints in this phase. These items are logged here and revisited
after the TypeScript conversion + hardening are finished.

Applied in Phase 3 (frontend-side, path only):

| # | File:line | Before | After | Backend (source of truth) |
|---|---|---|---|---|
| 1 | `src/lib/liveApi.js:781` | `GET /admin/gifts/settings` | `GET /admin/settings` | `admin_gifts.py:125` |
| 2 | `src/lib/liveApi.js:782` | `PATCH /admin/gifts/settings/:key` | `PATCH /admin/settings/:key` | `admin_gifts.py:141` |
| 3 | `src/lib/liveApi.js:1142` | `GET /admin/gifts/first-order-gifts` | `GET /admin/first-order-gifts` | `admin_gifts.py:21` |
| 4 | `src/lib/liveApi.js:1143` | `PATCH /admin/gifts/first-order-gifts/:id` | `PATCH /admin/first-order-gifts/:id` | `admin_gifts.py:52` |

These four were pure path corrections (the backend paths are also documented in
`BACKEND_SOURCE_OF_TRUTH.md` §1483/§1521/§2037/§2114).

## Open gaps (no frontend caller can succeed today)

| # | Frontend call (file:line) | Caller | Status | What is missing | Resolution when we revisit |
|---|---|---|---|---|---|
| G1 | `POST /orders/:id/resend-tracking` — `liveApi.js:173` | `pages/OrderDetail.jsx:94` (guest tracking email resend) | 404 | No backend route and no email/rate-limit implementation (the frontend comment claims a 5-min cooldown / 3-per-order limit that does not exist server-side). | Add backend handler **or** remove the button. |
| G2 | `POST /free-sides/redeem` — `liveApi.js:304` | `components/FreeSideRedemptionModal.jsx:32` (shown from `OrderDetail.jsx:520`) | 404 | Backend replaced the post-order redeem flow with cart-stage `POST /api/free-sides/select` (`free_sides.py:293-299`), consumed at checkout. **Verified: nothing in the frontend calls `/free-sides/select`** — no cart-stage free-side UI exists in this snapshot. The only free-side surfaces are this legacy modal and `FreeSideCreditModal.jsx` (a prompt that returns options via `featureConfig`). | Build the cart-stage selection UI against `/select`, or re-add a backend `/redeem`. |
| G3 | `GET /items/archived` — `liveApi.js:621` | `components/admin/AdminMenu.jsx:30` ("Archived" view) | 404 | Archive sets `deleted_at` (`menu.py:1039`), and `GET /menu/items` filters `deleted_at is null` — the backend cannot list archived items at all. | Add a backend filter/endpoint, or drop the admin archived view. |
| G4 | `GET /admin/free-credits` — `liveApi.js:1205` | `components/admin/AdminFreeCredits.jsx:25` (panel falls back to `[]`) | 404 | No read route; only `POST /api/free-sides/admin/credits` (grant) and `GET/POST/PATCH/DELETE /api/free-sides/admin/items` exist. | Add backend read route. |
| G5 | `GET /admin/exclusive-spin/history` — `liveApi.js:1219` | `components/admin/AdminExclusiveSpin.jsx:36` (falls back to `[]`) | 404 | No history route; closest is `GET /api/admin/exclusive-spin-prizes` (fulfilment queue, already called separately at `liveApi.js:1221`). | Add backend route, or repoint the panel at the prizes endpoint. |
| G6 | `POST /admin/reviews/:id/promote` — `liveApi.js:1059` | `components/admin/AdminReviews.jsx:67` | 404 | Only `GET /api/admin/reviews` exists; there is no promote write path and no confirmed `is_promoted`-style column. | Add backend handler after schema check. |
| G7 | `GET /settings` — `liveApi.js:1340` (`config.getPublic()`) | `lib/featureConfig.js:100` (public settings; silently falls back to defaults) | 404 | Real public endpoint is `GET /api/storefront/config/public` (flat `key → value` map). Caller expects `[{ key, value }]` rows, so a repoint also needs a small mapping change. | Repoint + map in `featureConfig.js`. |
| G8 | `GET /challenges/:id` — `liveApi.js:1305` | **no callers** (verified) | 404 | Retired subsystem; the method is unreachable. | Delete as dead code (Phase 6a). |

Admin panels for G3–G6 already degrade gracefully (`catch → []` / empty states), so none of these
calls crash a page today; they are logged as contract gaps, not regressions.
