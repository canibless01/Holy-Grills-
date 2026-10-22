export type BannerSlide = { image_url: string; mobile_image_url: string; eyebrow: string; title: string; subtitle: string; cta_text: string; cta_url: string; display_mode?: 'image' | 'text' };
export const blankBannerSlide = (): BannerSlide => ({ image_url: '', mobile_image_url: '', eyebrow: '', title: '', subtitle: '', cta_text: '', cta_url: '', display_mode: 'image' });

// Persist slide copy in the existing metadata JSON. Older rows keep their
// shared copy until an administrator edits them; no database backfill needed.
export function bannerSlides(b: any): BannerSlide[] {
  if (Array.isArray(b.metadata?.slides)) return b.metadata.slides.map((s: any) => ({ ...blankBannerSlide(), ...s }));
  const images = Array.isArray(b.images) && b.images.length ? b.images : [b.image_url].filter(Boolean);
  return images.map((image: any) => ({
    image_url: typeof image === 'string' ? image : image.url,
    mobile_image_url: b.mobile_image_url || '', eyebrow: b.metadata?.eyebrow || '',
    title: b.title || '', subtitle: b.subtitle || '',
    cta_text: b.action_label ?? b.cta_text ?? '', cta_url: b.action_url ?? b.cta_url ?? '',
  }));
}

export function bannerSlidePayload(slides: BannerSlide[], metadata = {}) {
  const first = slides[0] || blankBannerSlide();
  return { metadata: { ...metadata, slides }, images: slides.map(s => s.image_url).filter(Boolean),
    image_url: first.image_url, mobile_image_url: first.mobile_image_url,
    title: first.title, subtitle: first.subtitle, eyebrow: first.eyebrow,
    cta_text: first.cta_text, cta_url: first.cta_url };
}
