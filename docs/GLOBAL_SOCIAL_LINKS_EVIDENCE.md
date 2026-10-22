# Global social links — 21 October 2026

Super admins configure Instagram, Facebook, X, TikTok and YouTube under **System Settings → Social links**. Blank platforms remain hidden. The footer displays the configured icons directly; the Contact us disclosure and Contact page also display them. Campus WhatsApp support is unchanged.

The existing `system_settings` table stores one global `global_social_links` JSON value. No migration, new table or default production URL is needed. The form creates the key on its first save, publishes it, and reads it back before reporting success. Non-super administrators cannot write the global row; the API refuses campus-scoped social configurations even from a super admin. Public configuration always uses the global row and ignores historical campus overrides.

Both server and client validate HTTPS destinations against the selected platform's actual hostnames. Credentials, arbitrary hosts/ports, embedded whitespace and non-string settings are refused. Invalid historical settings remain hidden. External links have accessible platform labels and safe new-tab attributes. UI copy comes from `messages.py`.

Verification completed: seven focused backend tests, frontend TypeScript validation, owned-file ESLint, central-message registry check and whitespace validation passed. The tests exercise global configuration through the actual public-config route, campus-write refusal, first global creation, invalid destinations and historical invalid data. These are isolated tests without database mutations.

The parent ran the actual routed Playwright harness at `/workspace/work/ecosystem-audit/social-links-20261021/browser.py` successfully. All four controlled-browser cases passed:

- Super-admin creation saves one global configuration and verifies its read-back.
- Reload restores the configured links; an invalid destination produces an error without any write.
- The homepage footer and its Contact us disclosure render configured platform icons and hide unconfigured platforms.
- The Contact page displays accessible links at a mobile viewport with safe new-tab attributes.

Results are recorded in that private directory's `results.json`; the mobile screenshot is `contact-mobile.png`. The browser used real routed UI components with intercepted API fixtures, so this is UI-contract evidence, not live database publication or external social-service availability. Backend public-config/global-scope behavior was tested separately by the seven tests above. No real social URL has been configured or customer setting changed during this work.
