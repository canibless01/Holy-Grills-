# Community-manager sharing completion — 21 November 2026

Completed the owner-reported sharing follow-up. The recipient-read blocker is already pushed in `1b5b9a4`: the assignment table has no campus column, so scoped lookup now uses its existing ambassador relationship. Read-only production PostgREST verification on 16 November returned all 36 assigned recipients in the manager's campus. The schema/FK and live-read evidence are in `COMMUNITY_MANAGER_RECIPIENT_FIX_2026_11_16.md`.

Sharing now uses a normal WhatsApp link targeting the ambassador's saved phone, with normalized local/international numbering and their personalized referral caption. It works independently of script popup permission. Missing/invalid phone falls back to WhatsApp's contact chooser. The page explains that the graphic must be saved and attached separately; opening WhatsApp does not fabricate Shared status. Caption copying and manual pending/seen/shared controls remain available. A genuine empty recipient list is explicit.

Community managers can request a Cloudinary signature for the promotional uploader's exact folder. The server signs only `ambassador_promos/<their user id>` for that request. Other administrative image folders are not granted; profile uploads and existing admin/organizer paths retain their rules. No Supabase Storage, credentials in code, new column, migration or role broadening.

Verification completed before the environment restart; finalization resumes the unchanged verified source on 21 November:

- **1,949 full backend tests passed**; 103 targeted ambassador/upload cases include real authentication middleware, manager-scoped signatures, other-role/folder restrictions and existing programme permissions.
- Actual mobile/desktop promo workspace passes failed recipient read/Retry, direct WhatsApp target and exact caption/referral link, controlled new-tab navigation, graphic link, clipboard failure, rejected status write/retry, all three manual statuses, recipient lookup failure/retry, targeted promo creation and the actual image-uploader flow. Cloudinary transport is controlled; no genuine image/provider message is created.
- Roster/configuration suite passes campus admin, super admin and community manager cases, retaining manager roster/milestone reads and intended administrator-only configuration boundaries.
- Existing ambassador reward suite passes customer benefit/checkout, manager promo replay, manager monthly recommendation and admin grant replay cases. No real reward/order/message was created.
- WhatsApp link contract tests cover Nigerian/international normalization, missing-phone chooser and exact encoded text. TypeScript and component ESLint pass; the lib helper is ignored by the existing lint configuration and is checked by its executable contract, TypeScript and native integration.
- Complete contract/client/SSR/prerender production build passed.

The remaining acceptance is the manager's actual WhatsApp app/browser handing off and sending the message. No real WhatsApp message was sent, and production deployment success is not inferred from a local browser check. This does not mark the wider A1–A7 audit complete.
