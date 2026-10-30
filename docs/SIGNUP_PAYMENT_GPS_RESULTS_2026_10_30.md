# Signup, payment timing, rewards and GPS — 30 October 2026

## Corrected

- FUTA cutoff is database configuration, not a hardcoded hour: seven recurring ordering/operating-hour rows are 00:00–16:00 Africa/Lagos, linked to existing 19:30–20:30 delivery rules. Exact-cutoff/date-group regression checks were added in the preceding batch.
- Supabase reports `mailer_autoconfirm=true`. The app registration route nevertheless always discarded real issued sessions and returned `check_email`. It now returns genuine issued tokens for successful autoconfirm signup; the client persists them before reading identity and redirects Home. Duplicate/confirmation-required responses remain ambiguous and do not fabricate sessions.
- Welcome copy incorrectly read `welcome_bonus_hp` (first delivered order), while `signup_bonus_hp` was zero. Signup HP is now configured as 50, and the two owner-created accounts received the missing 50 active HP once through the normal deduplicated service. Future welcome notifications report actual grant receipts rather than configured promises. Signup gifts are flat, not multiplied by event bonuses, and campus-scoped. Existing first-delivery welcome configuration remains separate and was not removed.
- Both accounts already had one valid signup free-side credit; no duplicate side was granted. Actual authenticated API checks returned 50 active HP, zero pending HP and one credit for both accounts. Recovery now retries signup HP as well as the free-side grant and refreshes the balance afterward. Personal free-credit reads can resolve the owner's campus when a super admin has not selected an admin scope.
- `grillthevibe@gmail.com` is now `super_admin` in the authoritative profile. Sign out/in to refresh navigation. No other account role changed.
- Guest confirmation email moved from unpaid order creation to the verified paid transition. Existing replay/paid-state handling remains in place. Deferred confirmation at creation also requires paid state. An authenticated unpaid checkout can still receive the honest “Order saved / finish payment” notice; it is not payment confirmation.
- Public daily/window/item counters now count paid/partially-refunded orders. Internal admission reservations are retained to protect capacity; a saved unpaid checkout is not publicly reported as a paid order.
- Removed the added text block under the homepage hero. The supplied brand paragraph is used in business structured-data description, with a concise matching search/social description; no replacement paragraph was inserted into the storefront.
- Real deployed Google Maps SDK loaded and rendered a map, with no Google/CSP console errors; browser GPS emulation triggered the real fee request. Production permissions policy permits same-origin geolocation. This does not prove the owner's phone has allowed location. GPS now distinguishes permission denial and retries a coarse network fix when precise GPS times out. No Google Geolocation API/key is required for browser GPS.

## Validation and cleanliness

797 backend tests passed, followed by 17 focused payment/signup/counter/gift checks after the final paid-state condition. Frontend typecheck and full client/SSR/prerender build passed. An isolated browser signup test proves issued-session persistence and navigation to Home without an inbox prompt. All its HTTP was mocked; no real account was created. Google testing used a disposable browser-local guest cart and made no order/payment requests. Owner reward checks used existing owner accounts; temporary test login sessions were signed out with local scope. No test customers, orders or payments were inserted.

Existing referral, delivery reward, HP unlock, replay and ownership tests remain part of the full suite. No new live paid/referral/unlock fixtures were created in the cleaned production database. Those tests are not a claim of a new real-customer delivery cycle.

## Owner setup / remaining items

1. Copy Auth subjects/HTML from `SUPABASE_AUTH_EMAIL_TEMPLATES.md` into Supabase Authentication → Email Templates. SMTP is owner-configured; hosted Auth templates were not edited because no Auth management credential is connected. Email confirmation was not enabled.
2. Reviews integration expects the **Place ID itself** in Vercel `VITE_GOOGLE_BUSINESS_PLACE_ID`, followed by redeployment. A review URL is not interchangeable with that environment value.
3. Brevo fallback was **not implemented**, as requested. A dedicated Auth allowance is useful; multiple free accounts do not create a guaranteed pooled allowance. Brevo currently advertises 300 daily sends; all Auth/app sends on the same account share it. Keep current working Resend app routing while deciding on fallback capacity.
4. Google Maps key is now present. Owner physical-device GPS permission and notification-logo appearance remain device confirmations.
5. Search Console ownership/indexing request and the owned Google Business Profile/Place ID remain outstanding. Robots/sitemap/local metadata are fixed; no recrawl request was fabricated and rankings/autocomplete are not guaranteed.
6. OneSignal email approval remains a provider review item on/after 1 November 2026. App email defaults remain Resend and push remains OneSignal.

No backend hosting migration, SMTP-provider change, broadcast, new payment, or cleanup/deletion was performed in this round. Earlier migration instructions remain in `LAUNCH_DAILY_WINDOW_SEO_SMTP_MIGRATION_2026_10_30.md`.
