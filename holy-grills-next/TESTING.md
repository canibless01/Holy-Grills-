# How to test the Next.js pilot

The pilot is source code on main. It has not been published as a separate Vercel website by this work. Opening holygrills.online still opens the existing production frontend.

## Phone or browser: use a separate Vercel project

1. In Vercel choose **Add New → Project**, then import `canibless01/Holy-Grills-` again as a **new** project named, for example, `holy-grills-next-preview`. Keep the existing live project as it is.
2. Choose the **Next.js** framework. Set **Root Directory** to `holy-grills-next` and Node.js to **24.x**. Use `main` as the source branch.
3. Keep build/install defaults (`npm run build`, `npm install`); leave Output Directory at the Next.js default. Do not use the existing Vite `dist` setting.
4. Add these public endpoint settings to the new project:

   | Variable | Value |
   |---|---|
   | `API_BASE_URL` | `https://holygrills-production.up.railway.app/api` |
   | `LIVE_SITE_URL` | `https://holygrills.online` |
   | `NEXT_TELEMETRY_DISABLED` | `1` |

5. Deploy and open the new project's generated `vercel.app` URL. No custom domain is needed. Keep `holygrills.online` attached to the existing production project.
6. Test `/` and `/menu`. These are the only implemented pilot routes. All pilot pages intentionally stay noindex, including on the generated Vercel hostname.

Do not copy backend secrets, Supabase service-role keys, SMTP credentials or Paystack secret keys into this pilot. It only reads public data.

## What to try

- Open Home and check that the existing CMS hero copy/images appear. Swipe between slides or use the numbered slide links.
- Open Menu; compare item names/prices with the existing live site for the same campus.
- Search for a meal, change its category and submit **Find a meal**. A search with no matches should show a clear empty result.
- Check the same pages on a narrow mobile viewport; there should be no sideways page overflow.
- Disable JavaScript and reload Menu. Meal names and prices should still render; search/filter forms should still work.
- **Choose options** deliberately opens the existing live product page. It does not test a migrated Next.js cart or payment flow. Do not complete a real purchase just to test this handoff.
- Open `/admin` or `/checkout` on the pilot hostname: these routes are not migrated and return 404.

The initial local acceptance passed nine data tests and fifteen browser checks, plus read-only smoke checks against the live Railway public API. A new hosted preview still needs its own acceptance check. A local rendering pass is not a measured claim that every page is faster.

## Run on a computer

Install Node.js 24, clone this repository, and run:

```sh
cd Holy-Grills-/holy-grills-next
npm ci
cp .env.example .env.local
npm run build
npm run start -- --port 4140
```

Open `http://localhost:4140` and `http://localhost:4140/menu`. On Windows PowerShell, replace the `cp` line with `Copy-Item .env.example .env.local`.

This managed Codex workspace requires `NODE_USE_ENV_PROXY=1` before `npm run start` for outbound API reads. That local proxy setting is not needed on a normal Vercel deployment.

For automated checks, see [README.md](README.md#verification). Remaining migration work includes full public CMS parity, auth, cart, checkout, payment callbacks, notifications, PWA and staff pages.
