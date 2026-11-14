# CMS editing, recovery and sorting — 14 November 2026

Closed the requested follow-up batch for section/supporter editing and presentation/sorting recovery. A failed section save previously refreshed the list unconditionally and discarded the administrator's unsaved changes. Failure now retains the draft; retry stays available, and an explicit Reload saved content action is available when the administrator chooses to discard it. Section/supporter edits send the saved row version. Both endpoints reject stale drafts and condition their actual UPDATE on the selected version, including null legacy timestamps. Banner protection now also covers active/title/schedule-only changes, and the activation toggle sends its editor version. A race after the initial SELECT returns 409 rather than overwriting a newer save.

Supporter creation and saving suppress duplicate clicks; failed deletion is visible and recoverable. Create/edit modals do not close while their mutation is pending. Section editing preserves custom content fields. Supporter management reads return their timestamp without adding it to the public supporter representation. Existing scoped ordering RPCs remain authoritative; no rank table or new financial dependency was added.

CMS loading no longer starts newsletter administration reads on unrelated tabs or reloads newsletter data after unrelated section/supporter edits. Newsletter opens and refreshes its own feeds, with its pagers, test/create/cancel and unsubscribe behavior retained.

Evidence:
- 128 targeted backend tests, including new stale-draft and interleaved-save matrices for sections, supporters and banners; matching timestamps preserve custom fields.
- Full backend regression: 1,791 passed.
- Native Chromium at 393px and 1280px: equal-rank section/carousel move, reload persistence, stale-move error/recovery, failed section save retains draft, versioned save retry/persistence and explicit reload; no newsletter feed requests during these edits.
- Newsletter native regression at both widths/roles: read Retry, subscriber/campaign pagination, failed unsubscribe recovery, preview/create intent replay, detail text and cancellation pass after the loading change.
- Fresh production BEGIN/ROLLBACK: campus admin can update own CMS row; stale version affects zero rows; foreign/global writes are denied; student and inactive-admin writes are denied; super admin retains foreign/global access; custom content survives. Fixtures and accounts are rolled back. See `tests/sql/storefront_edit_scope_rollback.sql`.
- TypeScript, edited-component ESLint, message registry and full client/SSR/prerender build pass. Registry check retains existing fallback-text drift notices; no missing message key.

No schema migration, real content publication, customer message, price edit or retained fixture. Earlier public renderer/media evidence remains applicable; this batch is not a claim that every theoretical CMS/media provider condition was repeated.
