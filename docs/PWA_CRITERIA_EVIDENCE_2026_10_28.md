# PWA installability checks — 28 October 2026

This checkpoint distinguishes the production build served through the repository's host simulator from the live domain and the user's actual Chrome UI. It does not certify that a headless/mobile-emulated test displays Chrome's address-bar or Android menu installation entry.

## Checklist

| Criterion | Executed evidence |
| --- | --- |
| Manifest link/name | Exactly one /manifest.json link; name and short_name present; Chrome parses the production manifest |
| Required icons | General-purpose 192×192 and 512×512 PNGs return 200 with matching actual dimensions; maskable PNGs also pass dimensions and safe-area checks |
| Display/related apps | standalone; prefer_related_applications omitted |
| Start URL, identity and scope | All / on one origin; start URL returns 200 |
| Service worker | Actual production registration is activated, controls the page and has root scope; fetch handler exists |
| Asset hosting | Local production host applies repository header rules, correct MIME types and update headers. The live domain remains separately unverified |
| Secure context | Localhost browser secure-context check passes. Actual live HTTPS certificate, redirect chain and mixed-content behavior remain unverified in this environment |
| Engagement and existing install | Fresh persistent browser profiles; a real click and at least 32 seconds viewing. No synthetic install event in CDP diagnostics |
| Native promotion | Chrome reports zero technical installability errors locally. Headless tests did not emit beforeinstallprompt; visible desktop Chrome and actual Android promotion remain unresolved |

The framework is React with Vite, not Next.js. Worker registration is deliberately disabled/unregistered in Vite development to avoid stale source bundles. Installability diagnostics must use the production build, not npm run dev.

## Fixed

The worker cached manifest.json cache-first. Returning visitors could retain old install metadata despite HTTP no-cache headers. Changed the manifest to network-first with an offline fallback, prevented failed responses replacing valid cached metadata, and advanced the worker cache version to hg-v5. The real worker fetch-handler regression test covers warm-cache refresh, offline fallback, HTTP failure and no cached metadata.

The manifest also advertised /share as an installed share target, but the app has no receiver route. Removed that unsupported declaration rather than advertise a broken installed action. Its omitted enctype generated a noncritical Chrome warning; that warning was not an installation blocker. App identity, start URL and scope remain unchanged.

Manifest requirements and icon checks plus the worker-cache regression are now part of the build. Existing shared install-event handling and manual install-help UI tests pass; those controlled UI tests do not prove Chrome itself offers installation.

## Reproduction

Build with npm run build, then run:

    python scripts/diagnose-pwa-browser.py --output /tmp/pwa-check.json

The diagnostic uses Chromium's Page.getAppManifest and Page.getInstallabilityErrors on desktop and mobile-emulation profiles, records worker state, manifest/icon responses and real browser events, and asserts technical prerequisites. It does not inject an install event. A permitted environment can repeat against deployment:

    python scripts/diagnose-pwa-browser.py --origin https://holygrills.online --output /tmp/live-pwa-check.json

The live-domain request here failed at the managed outbound proxy with CONNECT 403, before reaching the site. The current environment policy still lists only backend/Supabase plus preset hosts. That is evidence about this audit environment, not an HTTP error from Holy Grills or proof of a customer-facing TLS failure. The installed user profile, actual deployed metadata/headers/certificate/redirects and Chrome device policies therefore still require a live check. Do not mark the reported native-install problem fixed solely from the local pass.

Chrome's menu installation and its automatic install promotion have different criteria. The fetch-handler requirement was removed for menu installation in Chrome 108 Android / 112 desktop. Engagement rules describe eligibility for promotion, not a guarantee that an icon appears exactly after 30 seconds. Android installation is generally offered through its menu/prompt; a desktop-style omnibox icon is not a universal Android requirement.

References: https://developer.chrome.com/blog/update-install-criteria and https://web.dev/articles/install-criteria .

No cron deployment, email-provider change or database cleanup was performed in this checkpoint.
