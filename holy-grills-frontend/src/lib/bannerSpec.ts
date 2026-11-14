/**
 * Banner frames — the single source of truth for every admin image surface.
 * ============================================================================
 * Every CMS card that takes an uploaded image renders into one of these frames.
 * The frame decides BOTH the shape it draws and the size an administrator should
 * design to, so the published dimensions can never drift from what ships:
 *
 *   • text mode     — the picture sits inset inside a rounded frame, with the
 *                     title, description and CTA button beside/below it;
 *   • artwork mode  — the design fills the entire rounded frame edge to edge
 *                     (no inner rectangle, no additional copy on top).
 *
 * Because the frame is width-driven (`aspect-ratio`, never a fixed pixel
 * height), the same upload scales up on a desktop container instead of being
 * locked to its phone size, and it is only ever cropped when the upload does
 * not match the frame's own proportions.
 *
 * Pure and import-free so `npm run test:banner-spec` can exercise the real
 * module, and shared by the storefront cards and the admin help text.
 */

export type BannerLayout = 'row' | 'stack';
export type BannerSpecId = 'compact' | 'wide' | 'feature' | 'strip';

export interface BannerSpec {
  id: BannerSpecId;
  /** `row` puts a square icon beside the copy; `stack` puts the picture above it. */
  layout: BannerLayout;
  /** CSS aspect-ratio for the artwork frame. */
  aspect: string;
  /** Human-readable ratio, e.g. "3:1". */
  ratio: string;
  /** Recommended design size — the frame's own proportions. */
  width: number;
  height: number;
}

/** Square image used by the icon/photo frame of a text card. */
export const BANNER_ICON_SIZE = 256;

export const BANNER_SPECS: Record<BannerSpecId, BannerSpec> = {
  // What's Inside — full-width row cards.
  compact: { id: 'compact', layout: 'row', aspect: '3 / 1', ratio: '3:1', width: 1200, height: 400 },
  // Homepage mid-page banners — stacked card, wide artwork.
  wide: { id: 'wide', layout: 'stack', aspect: '3 / 1', ratio: '3:1', width: 1200, height: 400 },
  // How It's Made + Promos on home/checkout — portrait-ish card.
  feature: { id: 'feature', layout: 'stack', aspect: '3 / 2', ratio: '3:2', width: 1200, height: 800 },
  // Menu + checkout banner strips + Promos on the menu page.
  strip: { id: 'strip', layout: 'row', aspect: '4 / 1', ratio: '4:1', width: 1600, height: 400 },
};

export const DEFAULT_BANNER_SPEC: BannerSpecId = 'feature';

export function bannerSpec(id: string): BannerSpec {
  return BANNER_SPECS[id as BannerSpecId] || BANNER_SPECS[DEFAULT_BANNER_SPEC];
}

/** StorefrontSlider variant → the frame that variant renders. */
export function storefrontSpecId(variant: string): BannerSpecId {
  if (variant === 'compact') return 'compact';
  if (variant === 'banner') return 'strip';
  return 'feature';
}

/** Banner API placement → the frame that placement renders. */
export function bannerPlacementSpecId(placement: string): BannerSpecId {
  return placement === 'home' ? 'wide' : 'strip';
}

/** Promo sections change shape with the page they are shown on. */
export function promoSpecId(placement: string): BannerSpecId {
  return placement === 'menu' ? 'strip' : 'feature';
}
