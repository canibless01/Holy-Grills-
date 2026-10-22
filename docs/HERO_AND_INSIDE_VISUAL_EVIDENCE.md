# Hero headline + What's Inside — evidence, 2026-10-22

Scope: visual-only refinement of the guest homepage hero and the What's Inside
row. No database migration, no CMS data write, no new endpoint.

## Changes

### Hero headline — white first phrase, then the gradient

`HeroCarousel` used to paint the entire hero title with the brand gradient. The
headline now runs **white → fire gradient**:

- the first phrase (and its own closing punctuation) is plain white;
- the remaining copy starts white too and only then melts into
  `#E70E0E → #F97316 → #F2B84B`, so the colour arrives gradually instead of
  starting mid-word;
- the split is copy-driven (`src/lib/heroTitle.ts`): explicit line break →
  first sentence → first comma clause → even word split, so no headline copy is
  hardcoded and no copy is lost;
- `hero-title-gradient` (a utility in `index.css`, token
  `--gradient-hero-title`) is used only by the hero placement. The menu and
  checkout artwork carousels and every other heading keep plain white.

### What's Inside cards

- Icon artwork now sits in a rounded, muted frame (`rounded-xl`, border, 6–8 px
  inner padding) instead of floating unboxed next to the copy.
- Full-artwork cards ("Full design image only") are inset inside the card with
  real margins on every side (10–12 px outer, 6–8 px inner, all rounded) and
  render with `object-contain`, so the uploaded design is never cropped or
  pushed to one side. The frame is centred and capped at 420 px so a 3:1
  artwork does not stretch the whole desktop row.
- Text cards keep their 104 px minimum so mixed rows do not stretch.

### Sign up action

- Every What's Inside card now carries a gradient **Sign up** pill that routes to
  `/register` (the section is guest-only on the homepage). The pill is inside the
  card button, so tapping the pill and tapping the card follow the same safe
  navigation helper (`openCmsDestination`).
- A CMS row that sets its own `cta_text` / `cta_url` still wins, and other
  storefront sections are unchanged — no destination or label is invented for
  them.
- Admin editor: the What's Inside tab's help text and the CTA placeholders now
  show the `/register` + "Sign up" default. New catalog key `FE_SF_SIGN_UP`.

## Verification

Local fixture-backed run (Vite dev server + a throwaway HTTP fixture for
banners/sections/media; production CMS data untouched):

- `npm run typecheck`: passed.
- `npm run lint` (`eslint . --quiet`): passed.
- `npm run messages:check`: every call site resolves; `FE_SF_SIGN_UP` added to
  the registry (the one pre-existing drift in `AdminExclusiveSpin.tsx` is
  unrelated and unchanged).
- `npm run test:hero-title`: **17 assertions pass** (sentence punctuation,
  question mark, ellipsis, explicit line break, comma clause, word split, empty
  and non-string input, no-copy-loss round trip). Wired into `npm run build`
  next to the other lib tests.
- `npm run test:value-text`, `npm run test:safe-navigation`: passed.
- `npm run routes:check`: `vercel.json` in sync (36 SPA route families).
- `python3 -m ast` parse of `messages.py`: MSG has 2,336 keys, no duplicates.
  Backend `unittest` suites were not run in this sandbox (Flask is not
  installed here); the change is one added string constant plus one reworded
  help string, and no backend test asserts either.

Measured in headless Chromium (1280 px and 430 px):

| Check | Result |
| --- | --- |
| Hero `<h1>` | white `Grilled with faith.` + one `.hero-title-gradient` span `Served with fire.` |
| Gradient | `linear-gradient(90deg, #FFF 0%, #FDE7CE 12%, #E70E0E 46%, #F97316 72%, #F2B84B 100%)`, `background-clip: text` |
| Other headings | 0 gradient spans (Squad Orders, Holy Points, section headers, Reviews) |
| Text card | 104–106 px tall, 64 px icon frame, gradient "Sign up" pill, `aria-label="<title> — Sign up"` |
| Full artwork | 960 × 320 upload rendered `object-contain` at 362 × 121 px (mobile) / 420 × 140 px cap (desktop), 12 px radius, transparent-to-muted frame, 10 px card margin |
| Card tap | `/register` for default cards, `/menu` for the row that sets its own destination |

Screenshots: `01-hero-headline-split.jpg`, `02-hero-mobile.jpg`,
`03-inside-card-mobile.jpg`, `04-inside-artwork-mobile.jpg`,
`05-inside-artwork-desktop.jpg` (in this folder). They come from the local
fixture, so the imagery and copy are placeholders, not production CMS content.

## Limits

The preview backend was a local fixture: it proves rendering, geometry and
routing, not production CMS publication. The default `/register` link is
client-side; the real CMS rows keep whatever destination an administrator saves.
