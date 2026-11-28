# Public contact, notification preferences and popup verification — 15 November 2026

## Changes

Contact reads now share a campus-keyed query across the contact page, contact controls and footer. A failed read shows an explicit Retry instead of implying that support configuration is empty. Retry restores all observers; requests capture their campus, follow account binding, and revalidate on return/reconnect without reloading forms. Account campus takes precedence over stale guest storage. WhatsApp remains campus-specific; email/socials remain configured global values. No floating contact button was added.

Preference reads ignore obsolete account/unmount responses. A failed partial update rolls back only that preference, preserving an independent successful push-enable update. A synchronous lock prevents duplicate category writes; pending controls stay disabled.

## Evidence and limits

- `scripts/test-contact-recovery-browser.py`: actual Contact/ContactActions/Footer with controlled HTTP; mobile/desktop member and mobile guest pass. Failed initial reads, Retry, shared restoration, account-versus-guest campus, campus selection, reload, WhatsApp/mail/social URLs and unsafe social-link omission. No provider navigation or real messages.
- `scripts/test-notification-preferences-browser.py`: mobile/desktop pass. Read failure/Retry, held category write, independent successful push enable, failed category rollback, all six single-field changes and reload persistence. Push SDK is stubbed: this proves UI/backend transport integration, not device delivery.
- `scripts/test-popup-flyer-browser.py`: five native cases pass: mobile guest, desktop guest, landscape guest, unselected guest and signed-in member. All five page placements, excluded page, daily receipt suppression/next-day repeat, revised content, campus isolation, CTA navigation, retained input, Escape/close and image/button geometry. Controlled irregular SVG keeps its aspect ratio and does not overlap actions. No popup product change was needed and Cloudinary byte delivery is not re-certified here.
- 16 existing preference/transport backend regressions passed. Latest full backend checkpoint remains 1,880 passing tests from the identity batch; it was not rerun merely for a message constant.
- TypeScript and edited-component ESLint passed; the existing lint configuration ignores the lib hook, which is covered by TypeScript, the production build and native tests. Complete client/SSR/prerender/contracts build passed.

No migrations, provider calls, permission changes or real customer/configuration writes were introduced. Whole-site sign-off and operational inbox/device observations are not implied by these finite assertions.
