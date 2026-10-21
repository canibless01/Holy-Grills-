# Storefront media repair evidence — 21 October 2026

This is a bounded repair of the reported storefront-image/save failures, paired with the section editor and menu-banner changes. It does not claim that the exact production network error has been captured or that every external Cloudinary operation has succeeded.

## Confirmed defects corrected

- When another section already owned a key, the request-UUID insert path incorrectly reported a changed saved-request conflict. It now returns the existing key-conflict response. The section editor separately uses independent stable keys, allowing multiple cards with the same visible title without collisions.
- Menu artwork banners no longer require an overlay title, subtitle or CTA. Two image-only slides can be created and edited; non-menu carousel slides retain their required title. Existing menu placement is recognized even when an update does not repeat it.
- Optimistic banner saves compare timestamp instants, so `Z` and `+00:00` representations of the same UTC instant do not create a false conflict. The final database update still compares the original authoritative timestamp, preserving actual concurrent-edit protection.
- A create request cannot hide an empty slide list behind a legacy main-image URL. Editing a carousel to remove all slides retains the existing intentional empty behavior.
- Tier icon management and rendering recognize legacy `tier_icon_<slug>` section keys when earlier records lack the newer explicit slug field. This allows the editor to update the saved row rather than attempting a duplicate create.

## Verification

Five focused media regressions passed, with 77 combined CMS test executions including the existing inherited publication/artwork tests. Frontend TypeScript validation and ESLint for the two changed tier files passed. No table, column, migration, Storage bucket or provider change was introduced; media remains Cloudinary-only.

The parent ran the journaled live harness against the actual backend and Supabase Test Two. **All 12 persistence/publication cases passed**: create, same-request replay, edit and anonymous read-back for eleven section rows covering process cards, What's Inside, Our Story, catering, promos, testimonials, share templates, tier icons and popup artwork, plus an image-only two-slide menu banner. Both process and What's Inside types used two independent rows, including an artwork-only row without a title. The menu save also accepted an equivalent UTC timestamp representation. See the [deidentified live results](STOREFRONT_MEDIA_LIVE_RESULTS.json).

The Cloudinary signature endpoint returned **503** because this audit backend still lacked `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET`. No real provider upload succeeded. The harness therefore used a trusted-cloud URL without a corresponding uploaded asset, explicitly labelled as URL persistence only. These successful database/API cases do **not** prove image loading, carousel rendering or external Cloudinary delivery. Four actual routed frontend checks subsequently passed with controlled API/assets: image-only 4:1 menu with no secondary headline, independent process cards with automatic advancement, compact text/design What’s Inside cards for a signed-in visitor, and two same-title cards created through the file-upload control with distinct saved keys. Provider responses/assets were intercepted in that UI proof; it does not close the real upload gate.

Only the isolated audit campus was used. All journaled fixture rows remain because cleanup is paused; no customer content was edited or deleted.

The editor now uses one stable unique key per draft, preserving retries while allowing same-title cards. What’s Inside is no longer hidden after login. How It’s Made and What’s Inside accept multiple entries; each is a separate scrolling card. Menu artwork uses 4:1 (1600 × 400 px recommended), with no overlay title requirement. Image/text mode controls are limited to consumers that support those modes.
