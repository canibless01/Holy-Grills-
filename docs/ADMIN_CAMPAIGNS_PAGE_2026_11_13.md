# Campaigns & Blasts page audit — 13 November 2026

Completed the recorded composer, history, analytics, own-account test, subscriber sync and recovery controls.

Fixed a cross-campus analytics exposure: the analytics route used the service client with no campaign authorization. It now uses the authenticated/RLS client plus exact selected/assigned campus filtering. The same scoped lookup protects detail, cancellation and retries. Lists have deterministic paging and validated status filters. Campus-less admins cannot use an unscoped read. The legacy deliverability route now shares the own-account durable preview contract instead of accepting arbitrary addresses and claiming success without a provider result.

Fixed the visible tracking toggle being discarded by rich-field validation. Its boolean now persists through create, test and request replay. Subscriber sync was another scope gap: direct account lookup and background batch sync now restrict to the operator's assigned/selected campus; a super-admin All Campuses view remains global, regardless of their original student campus. Invalid identifiers/ranges do not launch work. The UI accurately identifies the 500-account scope-limited batch.

Composer mutations, provider reviews and subscriber sync suppress duplicate clicks. Test and real-send UUIDs are independent, so an interrupted preview cannot consume the production campaign intent. Stale audience counts and history/analytics responses are discarded. Scheduled inputs explicitly use WAT, independent of the device timezone. Pending email tests no longer display false delivery success. Cancelled history has its own status; provider counts describe acceptance, and analytics identifies audience/activity rather than inventing inbox delivery or unique conversion. Rich previews render in the full-screen modal portal, remove executable markup/unsafe links and expose accessible close controls. CTA inputs fit mobile widths and respect the existing ten-button API limit.

Verification:
- Full backend suite: 1,771 passed.
- Fresh production BEGIN/ROLLBACK: campus/global/student/deactivated-account campaign isolation, restrictive segment-policy enforcement and denied foreign mutations. Existing dispatch capture/lease/privacy/review/replay matrix also passed on the live schema. No provider message or fixture persisted.
- Native Chromium at 393px/1280px: failed history read/Retry, both pages and status filter, analytics failure/Retry, stale audience response rejection, recipient selection, rich/plain fields, Cloudinary image URL binding, image alt/link, CTA label/link/style, tracking, safe HTML preview, sync duplicate suppression, interrupted own-account test, independent production request identity, duplicate-click/lost-response retry, WAT scheduling from a UTC browser and cancellation.
- Existing mobile/desktop provider-review form regression passed evidence validation and requeue reflection.
- TypeScript, edited-component ESLint and complete frontend build passed. No schema change or new periodic job.

Live inbox/device/provider acceptance remains an operational observation, separate from intercepted browser and rolled-back database evidence. Optional bulk email catch-up beyond the displayed batch remains bounded by the existing backend limit/offset API. No unrestricted mailing endpoint, external provider send or whole-admin certification is implied.

Next: ambassador roster/milestone administration, promo distribution and monthly review exceptions, followed by remaining storefront presentation/sorting variants. Prior reward/stock/event records remain completed for their documented cases.
