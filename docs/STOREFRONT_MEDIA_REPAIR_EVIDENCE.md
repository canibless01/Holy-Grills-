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

A journaled live harness at `/workspace/work/ecosystem-audit/storefront-live-20261021.py` separately attempts a real Cloudinary PNG upload and verifies create/replay/edit/anonymous read-back for process cards, What's Inside, Our Story, catering, promos, testimonials, share templates, tier icons, popup artwork and a two-slide menu banner. Its live result is recorded separately when run; a trusted image URL save alone is not rendered-asset or provider evidence. Only the isolated audit campus is used and all fixtures are retained because cleanup is paused.
