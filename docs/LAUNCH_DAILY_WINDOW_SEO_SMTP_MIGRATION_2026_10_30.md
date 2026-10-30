# FUTA daily preparation and launch setup — 30 October 2026

## Daily operation

Live configuration now has exactly one FUTA intake rule per weekday: **00:00 inclusive to 16:00 exclusive, Africa/Lagos**. All seven ordering rules retain links to their respective existing delivery rules, **19:30–20:30**. Operating hours were aligned to the intake hours. No delivery times were changed.

Seven-day read-only schedule verification confirms one intake window per day with those delivery times. The cleaned database currently contains zero FUTA orders. No test accounts, orders, payments or notifications were created. Tests use fake databases/local transport; production writes in this round were only the user-requested business-hour settings.

An order's ordering-window ID, delivery-window ID and preparation date identify its daily preparation group. Recurring weekday IDs are templates, not a single batch shared across all weeks. Kitchen queue, preparation totals and bulk advancement now use the same one-day WAT boundary, requiring a delivery window and paid/partially-refunded payment status. Today's kitchen window list has only today's occurrences, with an explicit date in the label. Older records remain in admin history; rider assignment remains a separate downstream delivery batch.

At 16:00 ordering is closed and the scheduling path offers the next bookable date. Boundary tests cover midnight, 15:59 and exactly 16:00. Date filtering protects against advancing a previous week's orders sharing the recurring window ID.

## Search visibility

Fixed a concrete crawl defect: both robots.txt and sitemap.xml advertised the obsolete holygrill.app domain. They now use https://holygrills.online. Static smoke checks verify the sitemap origin. Homepage/menu titles, description, visible homepage content and service-area structured data now explicitly describe Holy Grills, grilled food, community, FUTA, the Federal University of Technology Akure, Akure and Ondo State. Pages are prerendered with canonical metadata.

**No Google recrawl request was submitted.** Search Console ownership/access is not connected. The owner should verify the holygrills.online property at https://search.google.com/search-console, submit https://holygrills.online/sitemap.xml and inspect/request indexing for `/`, `/menu` and `/our-story`. Add the Search Console-provided verification TXT record if required; do not invent a verification token.

A verified, accurate Google Business Profile with FUTA/Akure service information is the next local-discovery step. Search rankings, broad searches such as “FUTA”, misspellings, autocomplete and AI Overview wording cannot be forced through geolocation tags or promised immediately. No GPS permission is needed for search visibility. References: [Google recrawl instructions](https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl), [local ranking factors](https://support.google.com/business/answer/7091).

## Email

Supabase Auth's password-reset request in this app calls Supabase's recovery endpoint. **Configure custom SMTP for production even while signup email confirmation is disabled.** Default Supabase SMTP is restricted and not a production delivery solution. Brevo SMTP is suitable after sender/domain verification; use the dashboard's SMTP host, port, login and SMTP key, not an assumed account password. Keep Auth link tracking disabled so reset links are not rewritten. [Supabase SMTP documentation](https://supabase.com/docs/guides/auth/auth-smtp).

Brevo's free plan is **300 sends/day**, not 400. Resend Free advertises 100/day and 3,000/month; using both could offer up to 400 on a day within both plans' limits, but Brevo Auth emails also consume its allowance. [Brevo limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan), [Resend pricing](https://resend.com/pricing).

Current app defaults for transactional/campaign email remain Resend; push remains OneSignal. Existing quota-only alternate email transport is OneSignal, **not Brevo**. Brevo backend fallback is not yet implemented/configured. Adding Brevo SMTP to Supabase configures only Auth emails; backend fallback needs separate credentials and an explicit integration, with switches only after a definite quota rejection, not an ambiguous timeout. Reserve capacity for password resets before marketing sends.

OneSignal sender-domain checks pass, but sending approval remains declined. Earliest notice re-evaluation date is 1 November 2026, using support@holygrills.online. Renaming a matching address does not correct an identified issue. The support draft in ONESIGNAL_EMAIL_REVIEW_2026_10_30.md remains unsent; the exact private rejection reason is unknown. Resend keeps app email independent of that pending approval.

## Moving only the backend from Render

1. Deploy the existing backend on the replacement host with its required environment variables: Supabase, JWT/SECRET_KEY, Paystack, OneSignal, Resend, Cloudinary and any Redis/worker configuration. Keep signing secrets unchanged during the move; do not expose them in Vercel browser variables.
2. In **Vercel**, change `VITE_API_BASE_URL` to `https://NEW-BACKEND/api`, then redeploy. The build also generates CSP from this value.
3. On the backend set `API_PUBLIC_URL=https://NEW-BACKEND/api`. Email tracking/unsubscribe paths now normalize either the origin or `/api` form consistently, avoiding a doubled `/api/api` after migration.
4. Keep backend `FRONTEND_URL=https://holygrills.online`; CORS must allow that frontend. These are browser/frontend URLs, not the new API URL.
5. Change Paystack's webhook destination to `https://NEW-BACKEND/api/webhooks/paystack`. Update Flutterwave's `/api/webhooks/flutterwave` if that provider is used. Check provider callbacks that actually target the old backend; frontend payment-return links stay on the frontend.
6. Check existing scheduler/worker deployments, monitoring and any Supabase Database Webhooks or Edge Functions that explicitly call the old API. Move/update those references if present. Do not assume moving the web server moves Celery/Redis/scheduled jobs.
7. **Supabase Auth Site URL and redirect allowlist stay on the frontend** when only the backend moves. The Supabase project URL/keys, OneSignal website origin, Google browser-key website restrictions and Google review destination remain unchanged unless their corresponding service/frontend also changes.
8. Verify health, login, quote, payment webhook and order tracking before retiring the old host. Preserve old-link reachability during transition where necessary.

Remaining dependencies: Google Maps key and real-provider test; Google Business Profile/Place ID; Search Console ownership and indexing request; Supabase SMTP setup; optional Brevo backend fallback; OneSignal approval review; physical-device notification appearance check. No backend hosting migration was performed in this round.
