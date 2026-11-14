# Storefront display and flyer timing — 22 October 2026

Homepage hero proportions remain unchanged: the accidental square request was retracted. Its existing CMS headline now uses the brand red → orange → gold gradient, and the artwork stays clearer at the top while a darker gradient rises from the bottom for text legibility. Process-card titles retain their normal text treatment.

Menu and checkout banner slides use the existing `metadata.slides` JSON, with an explicit artwork or text mode per slide. Artwork needs only its full image; the complete design is contained, not cropped, and an optional destination does not require invented overlay copy. Text cards require a title; the icon, description and paired action are optional. Each slide keeps independent content and rotates in a compact slot. What's Inside uses full-width compact icon/copy/action cards or complete artwork and remains guest-only through the homepage's existing guard. No table, migration or extra endpoint was added.

Flyer receipts now persist for 24 hours per campus, navigation page and flyer revision. A changed flyer becomes eligible immediately; a returning saved-login session is not permanently suppressed. Focus/visibility checks and a visible-page interval pick up revisions and expiry. The five supported placements remain home, menu, dashboard, orders and rewards. Existing full, uncropped transparent artwork behavior is preserved.

Early supporter actions now read Connect, use a real outlined button treatment, accept safe web/WhatsApp destinations and omit unsafe links. Server writes validate the actual supported social-link fields as well.

## Evidence

- 36 backend CMS contract test executions passed, including text-only and mixed-mode slides, per-mode required fields, legacy hero requirements, optional artwork destinations, independent copy and safe supporter links.
- Frontend TypeScript and owned component ESLint passed before the final label-only adjustments; the parent runs final integration checks.
- Parent ran `storefront-display-browser.py`: all five controlled actual-route cases passed (admin insertion, compact mixed-slide rotation, unchanged hero/gradient/Connect, 24-hour and revision behavior, all five popup pages). API/assets were intercepted; this is honest UI-contract evidence, not external upload proof. The final cosmetic labels were clarified from overlay title/subtitle to slide title/subtitle afterward, with the harness updated accordingly.
- Parent ran `storefront-display-live.py`: three real backend/Supabase cases passed: text-only two-slide creation, same-request replay, and anonymous independent-copy read-back. Only the existing owned audit campus was used; journaled banner retained, no cleanup.
- Actual frontend rendering of that persisted text-only carousel is being verified by `storefront-display-live-browser.py` on backend 5011/frontend 5197. The parent will record the outcome. No Cloudinary interception is needed for those text-only slides.
- Popup receipt boundary assertions (24 hours, revision, clock recovery, campus/page isolation) passed in the parent's runtime.

Actual Cloudinary provider upload/served artwork remains separately gated; no credential or provider configuration change is included.
