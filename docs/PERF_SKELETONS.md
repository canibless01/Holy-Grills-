# Loading skeletons — policy and measurement plan

The rule from the brief, applied per screen:

| Measured Flask latency (p50, warm) | Action |
|---|---|
| **< 100 ms** | Remove the skeleton — render directly (a skeleton that flashes for 40 ms is worse than none) |
| **100–300 ms** | Keep the skeleton |
| **> 300 ms** | Keep the skeleton **and** fix the endpoint (N+1, missing index, no caching) |

**No skeleton has been removed in this pass: that decision needs measurements, and the sandbox cannot reach the backend**
(its egress is allowlisted to the npm registry — every call to
`holy-grills-backend.onrender.com` fails before a socket opens, so any latency
number produced here would be fiction).

## How to measure (5 minutes, in your browser)

1. Open the running app and sign in with the role you want to measure.
2. Open DevTools → Console, paste **`holy-grills-frontend/tools/measure-api-latency.js`**, press Enter.
3. Walk the screens: Home → Menu → Item → Cart → Checkout → Orders → Rewards → Wallet → Leaderboard → Marketplace → Events → Profile, then `/admin` → each admin tab.
4. Run `__hgLatency.report()` — it prints endpoint, calls, p50, p95, max, non-2xx and the verdict from the table above.
   Use `__hgLatency.reset()` when you move between role sessions (student vs admin) so the two don't mix.

Cold-start caveat: the backend is on Render, so the **first** request after idle
can take 10–30 s (container spin-up). Take p50 from the *second* pass through a
screen; treat only warm numbers as the skeleton signal.

## What is already known statically

| Screen area | Backend shape | Expectation |
|---|---|---|
| Menu list / item detail | `GET /menu/items` (+ `/addons`) — indexed catalog reads | likely < 100 ms warm → skeleton candidates for removal |
| Home | several parallel calls (`kitchen-status`, storefront sections, featured items) | watch for duplicate on-mount fetches; p50 driven by the slowest of the fan-out |
| Rewards / Leaderboard / Wallet | aggregate reads over HP + wallet tables | 100–300 ms plausible → keep |
| Admin dashboards | `GET /admin/overview` style aggregates over orders/users | most likely > 300 ms → keep + optimise |

## Client-side wins already applied

- **Cart** no longer fires `getFreeSideCredits` on mount, and **Menu** no longer
  fires `getDeliveryWindowStatus` + `getKitchenCapacity` — their results were
  never read (removed in the 6a pass). Every removed on-mount call shortens the
  fan-out that the skeleton is waiting on.
- Route-level splitting means a screen's data fetch now overlaps its own chunk
  download instead of blocking on the whole app bundle.

## Endpoint-side follow-ups (Flask — needs your go-ahead, contract-touching)

These are candidates only; each must be confirmed with a real p95 before any
change, and schema/index work is explicitly out of bounds without approval:

1. **Duplicate/redundant round trips** — e.g. screens that fetch a list and then
   fetch a summary that the list already carries.
2. **N+1 patterns** in admin aggregates (per-row lookups on users/orders).
3. **Missing indexes** on the columns the admin tables sort/filter by
   (schema change → ask first).
4. **Caching headers** for the public catalog (`/menu/*`, `/storefront/*`) so
   repeat navigation is served from the browser/CDN cache instead of the origin.
