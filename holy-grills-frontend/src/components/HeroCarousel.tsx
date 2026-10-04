import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { liveApi } from '@/lib/liveApi';

interface HeroSlide {
  image: string;
  tag: string;
  sub: string;
  cta: string;
  cta_url?: string;
}

const DEFAULT_SLIDES: HeroSlide[] = [
  { tag: 'Grilled with Faith. Served with Love.', sub: 'Every plate is made with open flame and genuine care. Not a shortcut in sight — just the Holy Flame Method, every time.', cta: 'Feel the Difference', image: 'https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&q=80' },
  { tag: 'Real chicken. Real fire.', sub: 'Real flame, real flavour — never a flat top, never a reheat.', cta: 'See the Menu', image: 'https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=800&q=80' },
  { tag: 'Every order fuels your flame.', sub: 'Stack Holy Points, climb the leaderboard, unlock rewards.', cta: 'Start Earning', image: 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=800&q=80' },
];

// Build swipeable carousel slides from dedicated banners (placement='hero').
function buildSlidesFromBanners(banners: unknown): HeroSlide[] | null {
  if (!Array.isArray(banners) || !banners.length) return null;
  // Defensive: the backend can ignore the placement filter and return every
  // banner — keep only hero ones so other surfaces never leak into the hero.
  const active = banners.filter((b) => b.is_active !== false && (!b.placement || b.placement === 'hero'));
  const slides: HeroSlide[] = [];
  for (const b of active) {
    const imgs = Array.isArray(b.images) ? b.images : [];
    if (!imgs.length) continue;
    for (const img of imgs) {
      const url = typeof img === 'string' ? img : img.url;
      if (!url) continue;
      slides.push({
        image: url,
        tag: b.content?.headline || b.title || '',
        sub: b.content?.sub || b.content?.body || b.subtitle || '',
        cta: b.cta_text || 'Order Now',
        cta_url: b.cta_url || '/menu',
      });
    }
  }
  return slides.length ? slides : null;
}

function buildSlidesFromSections(sections: unknown): HeroSlide[] | null {
  if (!Array.isArray(sections) || !sections.length) return null;
  // Defensive: the backend ignores the section_type filter and returns ALL
  // storefront sections — keep only hero sections so share templates, promos,
  // etc. never leak into the hero carousel.
  const active = sections.filter((s) => s.is_active !== false && s.section_type === 'hero');
  if (!active.length) return null;
  return active.map((s) => ({
    image: s.content?.image_url || s.content?.image || s.image_url || 'https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&q=80',
    tag: s.content?.headline || s.content?.title || s.title || '',
    sub: s.content?.sub || s.content?.body || s.subtitle || '',
    cta: s.content?.cta || s.cta_text || 'Order Now',
    cta_url: s.cta_url || '/menu',
  }));
}

export default function HeroCarousel({ onCta }) {
  const navigate = useNavigate();
  const [slides, setSlides] = useState<HeroSlide[]>(DEFAULT_SLIDES);
  const [i, setI] = useState(0);
  const scrollRef = useRef(null);
  const autoTimer = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const loadHero = async () => {
      try {
        const banners = await liveApi.storefront.getBanners({ placement: 'hero' });
        if (!cancelled) {
          const fromBanners = buildSlidesFromBanners(banners);
          if (fromBanners) { setSlides(fromBanners); return; }
        }
        const sections = await liveApi.storefront.getSections({ section_type: 'hero' });
        if (!cancelled) {
          const fromSections = buildSlidesFromSections(sections);
          if (fromSections) setSlides(fromSections);
        }
      } catch { /* keep defaults */ }
    };
    loadHero();
    return () => { cancelled = true; };
  }, []);

  const scrollToSlide = useCallback((idx) => {
    const el = scrollRef.current;
    if (!el) return;
    const slide = el.children[idx];
    if (slide) el.scrollTo({ left: slide.offsetLeft, behavior: 'smooth' });
    setI(idx);
  }, []);

  useEffect(() => {
    if (slides.length <= 1) return;
    autoTimer.current = setInterval(() => {
      setI((p) => {
        const next = (p + 1) % slides.length;
        const el = scrollRef.current;
        if (el && el.children[next]) el.scrollTo({ left: el.children[next].offsetLeft, behavior: 'smooth' });
        return next;
      });
    }, 5000);
    return () => clearInterval(autoTimer.current);
  }, [slides.length]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || slides.length <= 1) return;
    const idx = Math.round(el.scrollLeft / el.clientWidth);
    if (idx !== i) setI(idx);
  }, [slides.length, i]);

  const s = slides[i % slides.length];
  const go = () => {
    const dest = s.cta_url || '/menu';
    if (onCta && dest === '/menu') onCta();
    else navigate(dest);
  };

  return (
    <div className="relative bg-foreground -mx-4 sm:-mx-6 lg:-mx-8 -mt-6 h-[78vh] min-h-[480px] overflow-hidden">
      {/* Swipeable image carousel — CSS scroll-snap for native touch swipe */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        onTouchStart={() => autoTimer.current && clearInterval(autoTimer.current)}
        className="flex h-full w-full overflow-x-auto snap-x snap-mandatory scrollbar-hide"
        style={{ scrollSnapType: 'x mandatory' }}
      >
        {slides.map((slide, idx) => (
          <div key={idx} className="relative shrink-0 w-full h-full snap-center overflow-hidden" style={{ scrollSnapAlign: 'center' }}>
            <img
              src={slide.image}
              alt={slide.tag || 'Holy Grill'}
              loading={idx === 0 ? 'eager' : 'lazy'}
              decoding="async"
              fetchPriority={idx === 0 ? 'high' : 'auto'}
              className={`absolute inset-0 w-full h-full object-cover ${idx === i ? 'animate-ken-burns' : ''}`}
            />
            {/* Legibility scrim only — a plain dark gradient, never a blur or
                frosted glass over the hero image. */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/25 to-transparent" />
          </div>
        ))}
      </div>

      {/* Overlay text — changes with the active slide */}
      <div className="absolute inset-0 px-4 sm:px-6 lg:px-8 pt-10 pb-8 flex flex-col justify-end pointer-events-none">
        {/* The one glass surface on the hero — the eyebrow pill. Fully
            transparent with a light backdrop blur + hairline border: no
            colour fill, only the hero image shows through it. */}
        <span className="inline-flex items-center gap-1.5 self-start px-3 py-1 rounded-full bg-transparent backdrop-blur-md border border-white/25 text-white text-xs font-bold mb-3 pointer-events-auto">
          🔥 FUTA's Only Flame Grill
        </span>
        <AnimatePresence mode="wait">
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          >
            <h1 className="font-heading font-extrabold text-4xl sm:text-5xl text-white leading-[1.05] mb-2 text-balance">{s.tag}</h1>
            <p className="text-base text-white/85 mb-5 max-w-md">{s.sub}</p>
          </motion.div>
        </AnimatePresence>
        <button
          onClick={go}
          className="self-start px-5 py-2.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-lg hover:scale-105 transition-transform pointer-events-auto"
        >
          {s.cta} →
        </button>

        {/* Dot indicators — horizontal, directly below the hero content */}
        {slides.length > 1 && (
          <div className="flex items-center gap-1.5 mt-4 self-end pointer-events-auto">
            {slides.map((_, idx) => (
              <button
                key={idx}
                onClick={() => scrollToSlide(idx)}
                aria-label={`Go to slide ${idx + 1}`}
                className={`rounded-full transition-all ${idx === i ? 'bg-primary w-6 h-1.5' : 'bg-white/50 w-1.5 h-1.5'}`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}