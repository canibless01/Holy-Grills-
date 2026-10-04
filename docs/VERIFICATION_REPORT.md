# Verification report — full-stack coverage (Base44-free build)

Static matrix generated from both codebases (`docs/coverage/*`).
Live checks that need the real backend and a real login are marked in §5.

## 1. Base44 removal — done

| Item | Resolution |
|---|---|
| `@base44/sdk` imports (`api/base44Client`, `lib/AuthContext`, `components/ProtectedRoute`, `lib/analytics`) | **Deleted** — all four were unreachable: `AuthContext`'s only consumer was `ProtectedRoute`, which had zero importers |
| `@base44/vite-plugin` | **Removed** from `vite.config.ts` + `package.json`; the `@ → src` alias it injected is now declared explicitly (`resolve.alias`) |
| `base44.auth.me()` in `lib/PageNotFound.tsx` | **Swapped** to `liveApi.auth.me()` → Flask `GET /api/auth/me` |
| `media.base44.com` image URLs (`FlameMark`, `lib/mascots`, `offline.html`, `ui/image.tsx`) | **Kept** — asset CDN, removing them breaks rendering |
| `appParams` (`VITE_BASE44_*`) | **Kept** — only `OAuthConsent` still reads it, for MCP endpoints that have **no Flask route** (see §4 stop-and-ask) |
| `app/config.py` CORS origin `…base44.app` | **Kept** — backend-side; removing may break a deployed origin |

Bundle impact: main chunk **1,353.81 kB → 1,222.40 kB** (−131.4 kB / −9.7%), gzip **373.98 → 330.11 kB** (−43.9 kB / −11.7%).

## 2. Coverage summary

- Flask routes registered: **401** (342 guarded, 59 public)
- Frontend calls: **419** — 409 correct, 8 with no Flask route, 2 MCP orphans
- Routes with a frontend caller: **359**; with none: **42**
- `/api/admin*` routes: **81**, guarded **81/81**

## 3. Frontend → Flask: the 8 calls with no route (stop-and-ask list)

| FE call (file:line) | Flask replacement? |
|---|---|
| `POST /api/orders/:id/resend-tracking` (`liveApi.ts:178`) | none — no email/rate-limit implementation server-side |
| `POST /api/free-sides/redeem` (`liveApi.ts:309`) | backend replaced it with cart-stage `POST /api/free-sides/select` |
| `GET /api/items/archived` (`liveApi.ts:626`) | none — archived rows are filtered out of `GET /menu/items` entirely |
| `POST /api/admin/reviews/:id/promote` (`liveApi.ts:1063`) | none — only `GET /api/admin/reviews` exists |
| `GET /api/admin/free-credits` (`liveApi.ts:1210`) | none — only the grant/items routes exist |
| `GET /api/admin/exclusive-spin/history` (`liveApi.ts:1224`) | none — closest is the prizes fulfilment queue |
| `GET /api/challenges/:id` (`liveApi.ts:1310`) | none — **no caller anywhere** (dead method, delete candidate) |
| `GET /api/settings` (`liveApi.ts:1346`) | real route is `GET /api/storefront/config/public` (flat map, needs a small mapper) |

Plus two relative fetches in `pages/OAuthConsent.tsx` (`/api/apps/:appId/mcp/consent-info`, `…/authorize-grant`):
**no Flask route exists.** In the Base44 build these were served by the Base44 platform. Decision needed:
port the MCP consent endpoints into Flask, or retire the page.

Note: 10 of the 12 contract gaps logged in `docs/PHASE3_CONTRACT_GAPS.md` are now proven by the matrix;
`/api/orders/suggestions` and `PATCH /api/admin/settings/<key>` **do** resolve (they were false alarms).

## 4. Admin-side read (static)

Backend: **every** `/api/admin*` route carries a guard (`require_auth` + `require_role`). Unique guards in use: `require_role`×242, `require_auth`×100.

Frontend: `pages/Admin.tsx` renders an **Access denied** screen and clears the session for any role outside
`admin`/`super_admin`; the check happens **before** any admin component mounts and **before** any admin data is fetched.
Link surfaces are role-conditional (`TopNav` only shows the staff button for staff roles).

| # | Admin section | Component | Endpoints called | Guarded | Public-by-design | Notes |
|---|---|---|---|---|---|---|
|---|---|---|---|---|---|
| 1 | `dashboard` | `AdminDashboard` | 5 | 4 | 1 | 1 public-by-design |
| 2 | `analytics` | `AdminAnalytics` | 11 | 11 | 0 |  |
| 3 | `economics` | `AdminEconomics` | 0 | 0 | 0 |  |
| 4 | `users` | `AdminUsers` | 9 | 9 | 0 |  |
| 5 | `orders` | `AdminOrders` | 8 | 8 | 0 |  |
| 6 | `wallet` | `AdminWalletTransactions` | 0 | 0 | 0 |  |
| 7 | `delivery` | `AdminDelivery` | 13 | 13 | 0 |  |
| 8 | `menu` | `AdminMenu` | 8 | 4 | 3 | 1 no-route / 3 public-by-design |
| 9 | `addons` | `AdminAddons` | 6 | 3 | 3 | 3 public-by-design |
| 10 | `events` | `AdminEvents` | 0 | 0 | 0 |  |
| 11 | `rewards` | `AdminRewards` | 1 | 0 | 1 | 1 public-by-design |
| 12 | `marketplace` | `AdminMarketplace` | 0 | 0 | 0 |  |
| 13 | `promos` | `AdminPromos` | 4 | 4 | 0 |  |
| 14 | `challenges` | `AdminChallenges` | 0 | 0 | 0 |  |
| 15 | `abandoned` | `AdminAbandonedCarts` | 2 | 2 | 0 |  |
| 16 | `orderlocks` | `AdminOrderLocks` | 1 | 1 | 0 |  |
| 17 | `freecredits` | `AdminFreeCredits` | 1 | 1 | 0 |  |
| 18 | `exclusivespin` | `AdminExclusiveSpin` | 1 | 1 | 0 |  |
| 19 | `hp` | `AdminHpMultipliers` | 3 | 2 | 1 | 1 public-by-design |
| 20 | `notifications` | `AdminNotifications` | 0 | 0 | 0 |  |
| 21 | `store` | `AdminStore` | 0 | 0 | 0 |  |
| 22 | `leaderboard` | `AdminLeaderboard` | 0 | 0 | 0 |  |
| 23 | `departments` | `AdminDepartments` | 0 | 0 | 0 |  |
| 24 | `storefront` | `AdminStorefront` | 0 | 0 | 0 |  |
| 25 | `reviews` | `AdminReviews` | 0 | 0 | 0 |  |
| 26 | `catering` | `AdminCatering` | 0 | 0 | 0 |  |
| 27 | `onboarding` | `AdminOnboarding` | 2 | 2 | 0 |  |
| 28 | `flags` | `AdminFeatureFlags` | 0 | 0 | 0 |  |
| 29 | `settings` | `AdminSystemSettings` | 3 | 3 | 0 |  |
| 30 | `academiccalendar` | `AdminAcademicCalendar` | 4 | 4 | 0 |  |
| 31 | `webhooks` | `AdminWebhooks` | 1 | 1 | 0 |  |
| 32 | `system` | `AdminSystem` | 3 | 2 | 1 | 1 public-by-design |

The **public-by-design** column counts endpoints an admin screen calls that carry no guard because the
data is public: `GET /menu/items`, `GET /menu/items/:id`, `GET /menu/items/:id/addons`, `GET /menu/categories`,
`GET /menu/kitchen-capacity`, `GET /hp/tiers`, `GET /health`. Guests hit the same routes, so no admin data is
exposed, and every admin-only write on those screens is guarded. **No unguarded route exists under `/api/admin*`.**

`AdminMenu`'s archived-items view is the one admin screen whose endpoint does not exist (`GET /items/archived`, §3);
it degrades to an empty list today.

## 5. What still needs a live browser/backed run (sandbox network is allowlisted)

| Check | Why it can't run here | How to run |
|---|---|---|
| Login → protected page → admin → logout, both roles | egress blocked: the sandbox reaches only the npm registry | the running dev preview, with a real account |
| Admin/user-side API responses (401/403, no data leak) | same | browser DevTools Network tab |
| Flask endpoint latency, Lighthouse/LCP, Slow-3G skeleton checks | same | Lighthouse against the deployed/preview URL |

## 6. How to regenerate

`docs/coverage/` is generated. Re-run `tools/coverage_matrix.py` after blueprint or `liveApi` changes.
