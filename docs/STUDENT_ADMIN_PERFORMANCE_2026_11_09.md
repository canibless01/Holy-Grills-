# Student and admin performance pass — 9 November 2026

Started by updating to `main` (`6e24c62`), preserving the owner's automatic
funding and streak-recovery fixes. Food items, prices, availability, catering,
takeout data, rewards configuration and production feature switches were not
changed. This pass creates no database rows or migrations.

## Changes

- Menu categories filter the loaded campus catalogue immediately. The same
  available-item request revalidates in the background when its existing
  15-second cache expires. Search immediately shows matching loaded items and
  keeps the debounced server lookup for discoverable secret items. An outage
  keeps known results with a retry message rather than blanking the grid.
- Published available-menu/category reads use the existing guest-readable API
  without waiting for an account refresh. Management reads, inactive categories
  and explicit secret-management reads retain authentication. Account/campus
  request isolation and live checkout validation remain in place.
- Menu/Home food cards request responsive Cloudinary image widths and modern
  formats. The first two menu photos load eagerly; later photos stay lazy.
  Signed, previously transformed, local and third-party image URLs retain their
  existing settings. One actual public photo measured **66,952 bytes → 20,336
  bytes** (JPEG → WebP at 480px), about **70% smaller**. This is one image
  measurement, not a whole-page speed claim.
- Menu stock and capacity helpers share one paid-order snapshot within a GET
  request. It is scoped by campus/day, never persists between requests, and is
  not reused during order/payment writes. This removes one duplicate database
  round trip without changing the existing capacity/counting rules.
- Admin Dashboard displays primary operational data as soon as it arrives;
  three slower reports no longer hold it behind a six-feed loading barrier.
  Reports have independent loading states, successful values survive refresh
  errors, overlapping scans are prevented, background tabs skip 30-second
  polling, and the whole-dashboard automatic retry burst was removed.
- Rewards loads challenges, free-side credits and exclusive-spin details
  independently, instead of delaying all three behind the slowest request.
  Intentionally disabled or unsupported optional features (403/404) do not
  produce a false reward-load failure; genuine outages remain retryable.
- CMS editing waits for its authoritative content/supporter reads, with
  newsletter reports loaded separately. Newsletter loading/errors cannot hide
  the CMS, falsely show zero subscribers or expose campaign controls before
  their data is known.
- Public and privileged settings load in parallel and commit atomically. Late
  responses cannot restore an older scope/session. Getters hide old-session
  values after logout. A failed read no longer masquerades as an empty settings
  table that permits writes.
- Settings writes have duplicate-submission guards and refresh client
  configuration. Campus admins create settings with their campus ID and can
  edit only their own campus rows; global creation keeps the super-admin
  behavior. The modal states the target scope.
- All refreshed reads after a write use a new in-flight request epoch. This
  prevents settings/flags/CMS and wallet/order refreshes from joining an older
  pre-write request. It does not introduce caching of financial reads.

## Evidence

- **1,360 backend tests passed**, including request-local stock/capacity sharing
  and non-reuse during financial writes.
- TypeScript and the full client/SSR/prerender build passed.
- `test-student-performance.mjs` is part of the build: image destination safety,
  published versus management authentication, settings refresh races, parallel
  settings reads, session changes and post-payment balance-read freshness.
- `test-page-performance-browser.py`: native Menu category/search/secret lookup,
  withheld dashboard reports, withheld/failing newsletter reports, failed
  settings read/retry, campus-scoped boolean updates and campus-admin creation.
  All HTTP is intercepted; no live settings or communications are changed.
- Existing native feature-flag acceptance passes: global switch/gate refresh,
  failed-write preservation, new flag creation, campus override visibility,
  campus-admin read-only controls, and read-error retry. No production switch
  was flipped.

The initial public Menu API sample took 2.31 seconds from this environment.
The changes remove unnecessary waits and reduce image bytes; private reads,
checkout prices and availability still depend on the live backend. No blanket
claim that every route is instantaneous is made.

## Audit status and next work

The owner confirmed physical-device acceptance is already complete. The earlier
synthetic Home hydration warning remains a separate investigation; this pass
does not certify the whole-site audit or all notification/provider crash-recovery
variants. The full existing backend suite remains passing.

After shipping this pass, the next authorized feature is wallet-to-wallet
transfers. The owner selected **same-campus recipients only**. Transfer money,
paired ledger entries, idempotency, receipts and permissions require their own
implementation and verification; they are not part of the performance changes.
