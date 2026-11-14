# Sunday notice, mobile PWA and remaining launch checks

## Sunday behaviour

- Sunday is calculated in Africa/Lagos, including when the visitor's device uses another timezone.
- Home uses its existing closed-window popup. Other customer pages show the Sunday notice; checkout keeps its existing scheduling/payment flow with Sunday-specific copy. Staff workspaces are excluded.
- When Monday is the next bookable day, the wording is:

  **We’re closed on Sundays**

  We don’t open on Sundays. Place your order today and we’ll prepare and deliver it on Monday.

  **Order for Monday** opens the existing date picker. The countdown says **Next delivery in**.
- If Monday is full or unavailable, the notice offers the next available delivery day instead. It cannot override server capacity or Sunday closures.
- Dismissal is scoped to campus, Sunday date and browser-tab session. A previous weekday dismissal cannot suppress Sunday's notice. Weekday popup wording is unchanged.
- Weekdays make no extra Sunday-status request. The plain status endpoint now shares the calendar's request-local configuration snapshot, avoiding repeated configuration reads while looking past closed days. Order/capacity reads remain fresh; no financial cross-request cache was introduced.

## Mobile PWA verification

Production `https://holygrills.online/` was checked in a persistent, non-incognito Chromium profile with Android mobile device settings:

- Manifest parse errors: **none**.
- Browser installability errors: **none**.
- Active worker: `https://holygrills.online/service-worker.js`, scope `https://holygrills.online/`.
- The earlier private-browser run reported only `in-incognito`; it did not identify a site manifest defect.
- Local browser checks verified the installation entry and appropriate help without a native prompt for Android, iPhone and iPad device conditions. These are UI checks in Chromium, not a claim of physical Safari installation.
- Modern iPads using a Macintosh user-agent now receive the mobile install banner too.
- Android help now explains that a regular browser tab is required; private tabs and some in-app browsers cannot install apps.
- Profile → **Install Holy Grills on this device** remains a manual entry point. iPhone/iPad users follow Safari → Share → Add to Home Screen.
- Manifest icon geometry, worker cache/lifecycle, TypeScript, Sunday WAT boundary tests and full production build/prerender passed. The backend suite passed **970 tests**.

## Entire-site launch status and full remaining list

The core ordering verification is recorded in [the pre-launch completion checklist](PRELAUNCH_COMPLETION_AND_CHECKLIST_2026_11_04.md): guest/wallet orders, payment-record replay, paid-only kitchen preparation, grouping, rider handoff, pickup and delivery passed real database checks with synthetic records rolled back. Seven old test orders were removed at the owner's request; accounts and wallet/payment records were preserved. No further code blocker was found in those exercised paths.

The following external/operational items remain to be completed or explicitly confirmed:

| Item | Current evidence / next step |
|---|---|
| Physical-device acceptance | Production Android-browser installability passed. Still check one actual Android install, Safari Add to Home Screen on an iPhone if supported, GPS permission/location selection, and notification tapping on the intended phone. No physical phone was available in this session. |
| Production payment acceptance | Confirm current Railway Paystack live-mode credentials and webhook destination, then complete one real payment/return/tracking round trip. This session did not inspect Railway secrets, charge a card or contact a payment provider. Earlier tests used controlled payment responses. |
| Google Business reviews | Confirmed missing in the production Vercel project's environment metadata: `VITE_GOOGLE_BUSINESS_PLACE_ID`. Supply the real Business Profile Place ID, add it to Vercel and rebuild. The Maps browser-key variable is present. Key values were not read. |
| Search Console / Google indexing | Ownership, sitemap submission and re-indexing requests were not performed or verified here. The earlier site metadata/sitemap changes are separate from Google's indexing and ranking decisions. |
| Authentication email acceptance | Supabase SMTP was reported configured. One actual password-reset email/link round trip and hosted branded-template application have not been verified here. Copy-ready templates are in `SUPABASE_AUTH_EMAIL_TEMPLATES.md`. No reset email was sent during this pass. |
| Deployment and hosting cost | Confirm API, worker and single beat scheduler are on the pushed code. The reduced cadence and single-process default are implemented; CLI/env overrides take precedence. Railway billing/resource metrics are not accessible in this session, so monetary savings are unmeasured. |
| First live rollover execution | Controlled weekly/monthly tests are complete. The next normal weekly archive is 9 November, 00:01 WAT; the monthly archive is 1 December, 00:01 WAT. Observe their execution then; replaying live-user rewards now is unnecessary. |

Google review/search setup and email styling are separate launch polish/discovery work. The payment, device and deployment rows are final operational acceptance checks. OneSignal email/push setup was left intact because the owner reported it resolved.
