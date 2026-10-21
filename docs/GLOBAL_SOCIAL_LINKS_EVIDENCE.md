# Global social links — 21 October 2026

Super admins configure Instagram, Facebook, X, TikTok and YouTube under **System Settings → Social links**. Blank platforms remain hidden. The footer displays the configured icons directly; the Contact us disclosure and Contact page also display them. Campus WhatsApp support is unchanged.

The existing `system_settings` table stores one global `global_social_links` JSON value. No migration, new table or default production URL is needed. The form creates the key on its first save, publishes it, and reads it back before reporting success. Non-super administrators cannot write the global row; the API refuses campus-scoped social configurations even from a super admin. Public configuration always uses the global row and ignores historical campus overrides.

Both server and client validate HTTPS destinations against the selected platform's actual hostnames. Credentials, arbitrary hosts/ports, embedded whitespace and non-string settings are refused. Invalid historical settings remain hidden. External links have accessible platform labels and safe new-tab attributes. UI copy comes from `messages.py`.

Verification completed: seven focused backend tests, frontend TypeScript validation, owned-file ESLint, central-message registry check and whitespace validation passed. The tests exercise global configuration through the actual public-config route, campus-write refusal, first global creation, invalid destinations and historical invalid data. These are isolated tests without database mutations.

A native routed Playwright harness with controlled API fixtures is prepared at `/workspace/work/ecosystem-audit/social-links-20261021/browser.py`; its browser verification remains pending until results are recorded. It covers the super-admin form, save/read-back, reload, invalid input, footer/disclosure links and mobile Contact layout. No real social URL has been configured or customer setting changed during this work.
