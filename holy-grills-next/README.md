# Next.js public-page pilot

An isolated, read-only migration experiment. **This is not the replacement frontend.**

Only `/` and `/menu` are implemented. They server-render the existing public Python API's campus-scoped menu and CMS hero slides. Product selection, accounts, cart, payments and staff tools remain on the existing live frontend. No database migration or provider change is required.

## Run

Use Node 24 and npm:

```sh
cd holy-grills-next
npm ci
cp .env.example .env.local
npm run build
npm run start -- --port 4140
```

`API_BASE_URL` is the public API base ending in `/api`; `LIVE_SITE_URL` is the existing frontend origin used for product/account handoff. Never put a Supabase service-role key or payment secret in this application.

For this managed workspace's outbound proxy, start Node with `NODE_USE_ENV_PROXY=1`. This is an environment-specific local requirement, not a production Vercel setting. The built-in Node proxy support is why Node 24 is specified.

## Verification

```sh
npm test
npm run typecheck
npm run build
npm run test:browser
```

The browser check requires Python 3 with Playwright and Chromium at `/usr/bin/chromium`. It starts a temporary **local fixture API** and the production Next server, then stops both. It checks SSR with JavaScript disabled, filters, price freshness, campus isolation, failed reads/retry, safe handoff and read-only behaviour. It never places orders, sends mail or changes the live database.

## Boundaries and caching

- Source calls are GET-only and constrained to five public resource paths. No authenticated proxy routes or server actions exist.
- Requests never forward browser tokens, cookies or arbitrary source URLs.
- Menu prices and availability use `no-store`. A repeated HTTP request observes a changed source price immediately.
- Public campus/CMS/category reads revalidate after 30 seconds. Campus is included in both the URL and `X-Campus-ID` header; request deduplication uses React's request-scoped `cache()`.
- Catalog and CMS requests run concurrently once the campus is resolved.
- Only selected menu fields enter the rendered UI/RSC payload. Internal cost/reward/contact fields are discarded.
- Images use the existing Cloudinary origin with explicit dimensions, responsive sizes and Cloudinary quality/width transformations. The font is local. Third-party trackers, push SDKs, maps, auth SDKs and role-specific bundles are not loaded.
- Search/categories use native GET forms, so they work before hydration and with JavaScript disabled.
- API errors show a retry/live-menu route, rather than made-up prices or a failed server page.
- CMS hero slides remain available through native horizontal scrolling and labelled slide links. Autoplay, other storefront sliders and full visual/interaction parity remain future work.
- Unknown campus slugs return 404. A product link returns to the live application, which remains authoritative for campus, options, current availability, price and payment.

## Safety and release scope

All routes always emit `noindex` metadata and an `X-Robots-Tag`; `robots.txt` disallows crawling. Do not disable these or attach the production domain yet. Private role/account routes are intentionally absent.

No production Vercel configuration, API implementation or database objects are changed. Do not merge this branch into main as a production cutover.

`lib/config.ts` is a small, pilot-only adapter of the existing frontend's central brand configuration. Extracting a framework-neutral shared brand package is pending; it should happen before the second frontend grows further.

## Next phases before replacing anything

1. Compare a separately hosted preview with the existing frontend using matched cold/warm network conditions. Local SSR success is not a speed claim.
2. Port the remaining public CMS sections and public detail routes; prove visual/content parity, accessibility, SEO metadata and canonical URLs.
3. Port authentication/session handling and campus persistence, then cart/product options and rewards, with no shared caching of private state.
4. Prove payment, cancellation/recovery, order tracking, notifications, PWA and staff-role workflows end to end.
5. Agree a staged cutover/rollback only after parity. Keep private pages authenticated and excluded from search indexing.
