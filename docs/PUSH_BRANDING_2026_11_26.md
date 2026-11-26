# Branded native notifications — 26 November 2026

The owner confirmed receiving the morning campaign push but reported that it was not recognisable as Holy Grills. Delivery/display for that observation is therefore confirmed; its visual presentation was a separate reported defect.

The shared push transport now adds a clear `Holy Grills ·` title prefix when the heading does not already contain the brand. Empty headings fall back to the brand name. The wording lives in messages.py. Existing branded titles are not doubled, and bodies, recipients, links, urgency and provider idempotency keys are preserved. This applies to new transactional and campaign pushes through the shared transport; email/in-app titles are unchanged.

Campaign rendering uses the same heading helper, so its admin server preview and newly captured messages agree with the final push title. The transport handles it idempotently. Existing prepared outbox payloads remain immutable during retries; already delivered notifications are not retrospectively changed or resent.

The existing red/gold application icon remains explicit for Chrome and Firefox. Chrome on Android also gets the existing transparent flame mark through `chrome_web_badge`, so its monochrome status-bar mark can carry the brand rather than defaulting to Chrome. The icon/mark assets were inspected and checked for availability, dimensions and alpha support. No image was redesigned or stored in Supabase. Native notification layout and supported icon placement remain controlled by the browser/OS.

Official field documentation checked: https://documentation.onesignal.com/reference/push-notification — chrome_web_icon, firefox_icon and chrome_web_badge (Android monochrome status-bar icon). No undocumented provider fields or duplicate worker/SDK were added.

Targeted tests cover branded and already-branded titles, empty headings, color icon and transparent badge URLs, unchanged recipient/key/deep link, and personalized preview/transport agreement. Existing notification retry/outbox/campaign/link tests remain passing. Full backend suite: 2,195 passed. Frontend message-registry validation passed; the preceding lifecycle batch passed typecheck, lint and full production build. No extra notification or customer-wide send was issued to test branding. The next genuinely due message after backend deployment can provide device appearance confirmation.
