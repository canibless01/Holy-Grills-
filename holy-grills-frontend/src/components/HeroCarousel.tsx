import CompactBannerCarousel from '@/components/storefront/CompactBannerCarousel';
import { bannerSlides } from '@/lib/bannerSlides';
import { msg } from '@/lib/messages';
import { useCampus } from '@/lib/campusContext';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { liveApi } from '@/lib/liveApi';
import { openCmsDestination } from '@/lib/safeNavigation';
import { heroTitleParts } from '@/lib/heroTitle';

interface HeroSlide {
  display_mode?: 'image' | 'text';
  eyebrow?: string;
  mobileImage?: string;
  image: string;
  tag: string;
  sub: string;
  cta: string;
  cta_url?: string;
}


// Build swipeable carousel slides from dedicated banners (placement='hero').
function buildSlidesFromBanners(banners: unknown, placement = 'hero'): HeroSlide[] | null {
  if (!Array.isArray(banners) || !banners.length) return null;
  // Defensive: the backend can ignore the placement filter and return every
  // banner — keep only hero ones so other surfaces never leak into the hero.
  const active = banners.filter((b) => b.is_active !== false && (b.placement || 'hero') === placement);
  const slides: HeroSlide[] = [];
  for (const b of active) {
    for (const slide of bannerSlides(b)) {
      if (!slide.image_url && slide.display_mode !== 'text') continue;
      slides.push({ image: slide.image_url, mobileImage: slide.mobile_image_url || undefined,
        display_mode: slide.display_mode, eyebrow: slide.eyebrow, tag: slide.title, sub: slide.subtitle,
        cta: slide.cta_text, cta_url: slide.cta_url });
    }
  }
  return slides.length ? slides : null;
}

function buildSlidesFromSections(sections: unknown): HeroSlide[] | null {
  if (!Array.isArray(sections) || !sections.length) return null;
  // Defensive: the backend ignores the section_type filter and returns ALL
  // storefront sections — keep only hero sections so share templates, promos,
  // etc. never leak into the hero carousel.
  const active = sections.filter((s) => s.is_active !== false && s.section_type === 'hero' && (s.content?.image_url || s.content?.image || s.image_url));
  if (!active.length) return null;
  return active.map((s) => ({
    image: s.content?.image_url || s.content?.image || s.image_url,
    eyebrow: s.content?.eyebrow || '',
    tag: s.content?.headline || s.content?.title || s.title || '',
    // Section rows keep subtitle/cta_* inside `content` (the columns are key,
    // section_type, title, content, is_active, sort_order) — read them there.
    sub: s.content?.sub || s.content?.body || s.subtitle || s.content?.subtitle || '',
    cta: s.content?.cta || s.content?.cta_text || s.cta_text || msg('FE_STOREFRONT_ORDER_NOW', 'Order Now'),
    cta_url: s.content?.cta_url || s.content?.cta_link || s.cta_url || '/menu',
  }));
}

export default function HeroCarousel({ onCta = undefined, placement = 'hero' }) {
  const navigate = useNavigate();
  const SlideHeading = placement === 'hero' ? 'h1' : 'h2';
  const artworkOnly = placement === 'menu' || placement === 'checkout';
  const { campusId } = useCampus();
  const [slides, setSlides] = useState<HeroSlide[]>([]);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef(null);
  const autoTimer = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setSlides([]);
    setI(0);
    const loadHero = async () => {
      try {
        const banners = await liveApi.storefront.getBanners({ placement });
        if (!cancelled) {
          const fromBanners = buildSlidesFromBanners(banners, placement);
          if (fromBanners) { setSlides(fromBanners); return; }
        }
        if (placement !== 'hero') { if (!cancelled) setSlides([]); return; }
        const sections = await liveApi.storefront.getSections({ section_type: 'hero' });
        if (!cancelled) {
          const fromSections = buildSlidesFromSections(sections);
          setSlides(fromSections || []);
        }
      } catch { if (!cancelled) setSlides([]); }
    };
    loadHero();
    return () => { cancelled = true; };
  }, [campusId, placement]);

  const scrollToSlide = useCallback((idx) => {
    const el = scrollRef.current;
    if (!el) return;
    const slide = el.children[idx];
    setPaused(true);
    if (slide) el.scrollTo({ left: slide.offsetLeft - (el.children[0]?.offsetLeft || 0), behavior: 'instant' });
    setI(idx);
  }, []);

  useEffect(() => {
    if (artworkOnly || slides.length <= 1 || paused) return;
    autoTimer.current = setInterval(() => {
      setI((p) => {
        const next = (p + 1) % slides.length;
        const el = scrollRef.current;
        if (el && el.children[next]) el.scrollTo({ left: el.children[next].offsetLeft - (el.children[0]?.offsetLeft || 0), behavior: 'instant' });
        return next;
      });
    }, 5000);
    return () => clearInterval(autoTimer.current);
  }, [slides.length, paused, artworkOnly]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || slides.length <= 1) return;
    const idx = Math.round(el.scrollLeft / el.clientWidth);
    if (idx !== i) setI(idx);
  }, [slides.length, i]);

  if (!slides.length) return null;
  if (artworkOnly) return <CompactBannerCarousel slides={slides} />;
  const s = slides[i % slides.length];
  // The hero keeps its first phrase white and lets the rest of the headline
  // run into the brand gradient. Other placements stay plain white.
  const title = placement === 'hero' ? heroTitleParts(s.tag) : { lead: s.tag, tail: '' };
  const go = () => {
    const dest = s.cta_url || '/menu';
    if (onCta && dest === '/menu') onCta();
    // S8 — external links open in a new tab, internal ones route.
    else openCmsDestination(dest, navigate);
  };

  return (
    <div className={placement === 'hero' ? 'relative bg-foreground -mx-4 sm:-mx-6 lg:-mx-8 -mt-6 h-[78vh] min-h-[480px] overflow-hidden' : artworkOnly ? 'relative rounded-xl aspect-[4/1] overflow-hidden' : 'relative bg-foreground rounded-2xl h-72 sm:h-80 overflow-hidden'}>
      {/* Swipeable image carousel — CSS scroll-snap for native touch swipe */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        onTouchStart={() => setPaused(true)}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        className="flex h-full w-full overflow-x-auto snap-x snap-mandatory scrollbar-hide"
        style={{ scrollSnapType: 'x mandatory' }}
      >
        {slides.map((slide, idx) => (
          <div key={idx} className="relative shrink-0 w-full h-full snap-center overflow-hidden" style={{ scrollSnapAlign: 'center' }}>
            <picture>
            {slide.mobileImage && <source media="(max-width: 767px)" srcSet={slide.mobileImage} />}
            <img
              src={slide.image}
              alt={slide.tag || 'Holy Grill'}
              loading={idx === 0 ? 'eager' : 'lazy'}
              decoding="async"
              {...({ fetchpriority: idx === 0 ? 'high' : 'auto' } as { fetchpriority: string })}
              className={`absolute inset-0 w-full h-full ${artworkOnly ? 'object-contain' : `object-cover ${idx === i ? 'animate-ken-burns' : ''}`}`}
            />
            </picture>
            {/* Legibility scrim only — a plain dark gradient, never a blur or
                frosted glass over the hero image. */}
            {!artworkOnly && <div className="absolute inset-0 bg-[linear-gradient(to_top,rgba(0,0,0,0.88)_0%,rgba(0,0,0,0.6)_36%,rgba(0,0,0,0.16)_72%,transparent_100%)]" />}
            {artworkOnly && slide.cta_url && <button type="button" onClick={() => openCmsDestination(slide.cta_url, navigate)} aria-label={slide.tag || msg('FE_MENU_BANNER_OPEN', 'Open banner')} className="absolute inset-0 w-full h-full" />}
          </div>
        ))}
      </div>

      {/* Overlay text — changes with the active slide */}
      <div className="absolute inset-0 px-4 sm:px-6 lg:px-8 pt-10 pb-8 flex flex-col justify-end pointer-events-none">
        {/* The one glass surface on the hero — the eyebrow pill. Fully
            transparent with a light backdrop blur + hairline border: no
            colour fill, only the hero image shows through it. */}
        {!artworkOnly && s.eyebrow && <span className="inline-flex items-center gap-1.5 self-start px-3 py-1 rounded-full bg-transparent backdrop-blur-md border border-white/25 text-white text-xs font-bold mb-3 pointer-events-auto">{s.eyebrow}</span>}
        {!artworkOnly && <>
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          >
            <SlideHeading className="font-heading font-extrabold text-4xl sm:text-5xl text-white leading-[1.05] mb-2 text-balance">
              {title.lead}
              {title.tail && <>{' '}<span className="hero-title-gradient">{title.tail}</span></>}
            </SlideHeading>
            <p className="text-base text-white/85 mb-5 max-w-md">{s.sub}</p>
          </motion.div>
        </>}
        {!artworkOnly && s.cta && s.cta_url && <button
          onClick={go}
          className="self-start px-5 py-2.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-lg hover:scale-105 transition-transform pointer-events-auto"
        >
          {s.cta} →
        </button>}

        {/* Dot indicators — horizontal, directly below the hero content */}
        {slides.length > 1 && (
          <div className="flex items-center gap-1.5 mt-4 self-end pointer-events-auto">
            {slides.map((_, idx) => (
              <button
                key={idx}
                onClick={() => scrollToSlide(idx)}
                aria-label={msg('FE_CMS_GO_TO_SLIDE', 'Go to slide {number}', { number: idx + 1 })}
                className={`rounded-full transition-all ${idx === i ? 'bg-primary w-6 h-1.5' : 'bg-white/50 w-1.5 h-1.5'}`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
