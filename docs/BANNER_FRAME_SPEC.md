# Banner frames — one card format for every admin image input

**Status:** shipped on this branch. Frontend-only; no migration, endpoint or CMS
write.

## The format

Every admin surface that takes an uploaded image now renders through one shell
(`src/components/storefront/BannerCard.tsx`). There are exactly two modes and
one outer frame — `rounded-2xl` (16 px), `overflow-hidden`, hairline border:

| Mode | What it looks like |
| --- | --- |
| **Image or icon with text** (`text`) | The picture sits in its own rounded frame inside the card; the eyebrow, badge, title and description sit beside it (`row` frames) or below it (`stack` frames); a gradient button carries the CMS CTA link. |
| **Full design image only** (`artwork`) | The uploaded design fills the **whole** rounded frame, edge to edge. No inner rectangle, no letterboxing, no extra copy on top. Corners come from the frame, so designs are uploaded square-cornered. |

The frame is **width-driven** (`aspect-ratio`, never a fixed pixel height), so
the same upload scales with its container: a desktop card is proportionally
larger than the phone card instead of being pinned to phone dimensions.

## Design dimensions — give these to whoever makes the artwork

These numbers live in `src/lib/bannerSpec.ts` and are the same numbers the admin
help text prints, so a brief can never drift from what ships.

| Frame | Used by (admin tab → surface) | Ratio | Design size | Layout |
| --- | --- | --- | --- | --- |
| `compact` | What's Inside | 3:1 | **1200 × 400 px** | row (icon + copy + CTA) |
| `wide` | Banners (`home`) | 3:1 | **1200 × 400 px** | stacked |
| `feature` | How It's Made; Promos on Home and Checkout | 3:2 | **1200 × 800 px** | stacked |
| `strip` | Menu Banners; Checkout Banners; Promos on the Menu page | 4:1 | **1600 × 400 px** | row |
| icon | Text-mode cards on any of the above | 1:1 | **256 × 256 px** | square, rounded by the frame |

Rules for artwork in **Full design image only** mode:

1. Export at exactly the size above — that is the frame's own proportion, so
   nothing is cropped.
2. Upload **square corners**. The frame applies the 16 px radius.
3. Keep text and logos inside a **40 px safe margin**; the rounded corners eat
   into the outer edge.
4. PNG for flat colour or transparency, JPEG (quality 80+) for photography.

A design at a different ratio is still accepted; it is centre-cropped to the
frame, so anything important near the edge can be lost.

## Where it applies

- **What's Inside** — `StorefrontSlider` (`compact`)
- **How It's Made** — `StorefrontSlider` (`landscape` → `feature`)
- **Promos** — `StorefrontSlider` (`poster` → `feature` on Home/Checkout,
  `banner` → `strip` on the Menu page)
- **Hero, Banners (home), Menu Banners, Checkout Banners** — `AdminBanners` →
  `CompactBannerCarousel` (`wide` for Home banners, `strip` for Menu/Checkout)
- **Catering** — `CateringCard` (`feature`)

The immersive homepage **hero slider** keeps its full-bleed overlay design — it
is the one surface that is not a card, and the brief above does not apply to it.
Our Story's 16:9 hero and the transparent popup flyer also keep their existing
presentation.

## Admin experience

Every image input on those tabs now shows the **Design to the frame** note with
the exact pixel size and ratio for that tab (text from `BannerSpecNote.tsx`,
numbers from `bannerSpec.ts`). Editing a Promo (or creating a section) shows the
same note so the size is visible before the upload.

## Verification

- `npm run build` (typecheck → lint → messages → `test:banner-spec` →
  `test:hero-title` → lib tests → client + SSR build → pre-render): **passed**.
- `npm run test:banner-spec`: **46 assertions** — published ratio matches the
  pixel size, `aspect-ratio` mirrors the design size, every fallback resolves,
  and each surface maps to its documented frame.
- Headless Chromium, same component at 430 px and 1080 px:

| Frame | Mobile | Desktop |
| --- | --- | --- |
| `strip` artwork | 398 px wide | 1040 px wide |
| `wide` artwork | 398 px wide | 1040 px wide |
| `feature` artwork | 398 px wide | 440 px card, 438 px image |
| artwork image | `object-fit: cover`, fills frame | same, scaled |
| card radius | 16 px | 16 px |
| text card CTA | gradient pill present | same |

Screenshots in this folder: `01-frames-desktop.jpg` (all five frames at once),
`02-frames-mobile.jpg`, `03-inside-row.jpg`, `04-promo-and-home-banner.jpg`.
They come from a local fixture, so the imagery and copy are placeholders.

## Limits

The local fixture can render the card component in isolation but cannot boot the
whole Menu page (it needs live catalogue data), so the Menu-page strip is proven
by the component harness above plus the shared code path, not by a full page
screenshot. Production CMS publication is unchanged; existing rows keep their
stored `display_mode`.
