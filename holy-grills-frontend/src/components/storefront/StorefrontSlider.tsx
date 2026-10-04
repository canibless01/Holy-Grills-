import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useNavigate } from 'react-router-dom';
import { openCmsDestination } from '@/lib/safeNavigation';

// Each homepage slider gets its own visual identity so the page doesn't feel
// like the same card repeated four times. Images are power-clipped via
// object-cover so any upload dimensions fill the card cleanly.
//   portrait  — 4:5, text overlaid on image, 3-up desktop  (What's Inside)
//   landscape — 3:2, text overlaid on image, 2-up desktop  (How It's Made)
//   poster    — 3:2, text below image in a card, 2-up      (Catering)
const VARIANTS = {
  portrait: {
    aspect: '4 / 5',
    cardClass: 'w-[68vw] sm:w-[calc((100%-1.5rem)/3)]',
    maxW: 300,
    textBelow: false,
  },
  landscape: {
    aspect: '3 / 2',
    cardClass: 'w-[80vw] sm:w-[calc((100%-0.75rem)/2)]',
    maxW: 440,
    textBelow: false,
  },
  poster: {
    aspect: '3 / 2',
    cardClass: 'w-[80vw] sm:w-[calc((100%-0.75rem)/2)]',
    maxW: 440,
    textBelow: true,
  },
};

export default function StorefrontSlider({ sectionType, variant = 'portrait', eyebrow, headline, subline, loggedInOnly = false }) {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [slides, setSlides] = useState(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef(null);

  const v = VARIANTS[variant] || VARIANTS.portrait;

  useEffect(() => {
    let live = true;
    getStorefrontSections(sectionType)
      .then((list) => {
        if (!live) return;
        const arr = (Array.isArray(list) ? list : [])
          .filter((s) => s.is_active !== false)
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        setSlides(arr);
      })
      .catch(() => { if (live) setSlides([]); });
    return () => { live = false; };
  }, [sectionType]);

  const reducedMotion = typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

  const scrollTo = useCallback((idx) => {
    const el = scrollRef.current;
    if (!el) return;
    const card = el.children[idx];
    if (card) el.scrollTo({ left: card.offsetLeft, behavior: 'smooth' });
    setActive(idx);
  }, []);

  // Auto-advance + loop. The `paused` flag stops/restarts the interval cleanly —
  // no manual timer juggling. Stays still for reduced-motion users.
  useEffect(() => {
    if (!slides || slides.length <= 1 || reducedMotion || paused) return;
    const timer = setInterval(() => {
      setActive((p) => {
        const next = (p + 1) % slides.length;
        const el = scrollRef.current;
        if (el && el.children[next]) el.scrollTo({ left: el.children[next].offsetLeft, behavior: 'smooth' });
        return next;
      });
    }, 4500);
    return () => clearInterval(timer);
  }, [slides, reducedMotion, paused]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !slides || slides.length <= 1) return;
    const idx = Math.round(el.scrollLeft / (el.children[0]?.offsetWidth || 1));
    if (idx !== active && idx >= 0 && idx < slides.length) setActive(idx);
  }, [slides, active]);

  const handleTap = (slide) => {
    const dest = slide.cta_url || slide.content?.destination || '/menu';
    if (loggedInOnly && !isAuthenticated) {
      navigate(`/login?returnTo=${encodeURIComponent(dest)}`);
    } else {
      // S8 — external links open in a new tab, internal ones route.
      openCmsDestination(dest, navigate);
    }
  };

  if (!slides) {
    return (
      <section className="space-y-3">
        <Header eyebrow={eyebrow} headline={headline} subline={subline} />
        <div className="flex gap-3 overflow-hidden">
          {[0, 1, 2].map((i) => (
            <div key={i} className={`rounded-2xl bg-card border border-border animate-pulse ${v.cardClass}`} style={{ aspectRatio: v.aspect, maxWidth: v.maxW }} />
          ))}
        </div>
      </section>
    );
  }
  if (slides.length === 0) return null;

  return (
    <section className="space-y-3">
      <Header eyebrow={eyebrow} headline={headline} subline={subline} />
      <div
        ref={scrollRef}
        onScroll={onScroll}
        onTouchStart={() => setPaused(true)}
        onTouchEnd={() => setPaused(false)}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        className="flex gap-3 overflow-x-auto scrollbar-hide snap-x snap-mandatory -mx-1 px-1"
        style={{ scrollSnapType: 'x mandatory' }}
      >
        {slides.map((s, i) => {
          const img = s.image_url || s.content?.image_url || '';
          const title = s.title || s.content?.title || '';
          const line = s.subtitle || s.content?.line || s.content?.subtitle || '';
          const badge = s.content?.badge || s.badge || '';
          return (
            <button
              key={s.id || i}
              onClick={() => handleTap(s)}
              className={`relative shrink-0 snap-start overflow-hidden rounded-2xl text-left group ${v.cardClass} ${v.textBelow ? 'flex flex-col bg-card border border-border' : 'bg-foreground'}`}
              style={{ maxWidth: v.maxW, scrollSnapAlign: 'start' }}
            >
              {v.textBelow ? (
                <>
                  <div className="relative overflow-hidden" style={{ aspectRatio: v.aspect }}>
                    {img && <img src={img} alt={title} loading={i < 3 ? 'eager' : 'lazy'} decoding="async" className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />}
                  </div>
                  <div className="p-3 flex-1">
                    {badge && <span className="inline-block mb-1 px-2 py-0.5 rounded-full bg-accent/20 text-accent-foreground text-[9px] font-extrabold uppercase tracking-wide">{badge}</span>}
                    {title && <h3 className="font-heading font-extrabold text-sm text-foreground leading-tight line-clamp-2">{title}</h3>}
                    {line && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{line}</p>}
                    <span className="inline-flex items-center gap-1 mt-1.5 text-[11px] font-bold text-primary">Explore <ChevronRight className="w-3.5 h-3.5" /></span>
                  </div>
                </>
              ) : (
                <>
                  {img && <img src={img} alt={title} loading={i < 3 ? 'eager' : 'lazy'} decoding="async" className="absolute inset-0 w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-transparent" />
                  <div className="absolute inset-0 p-4 flex flex-col justify-end">
                    {badge && <span className="self-start mb-2 px-2.5 py-1 rounded-full bg-accent text-accent-foreground text-[10px] font-extrabold uppercase tracking-wide">{badge}</span>}
                    <motion.div key={i} initial={{ opacity: 0, y: 8 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.4 }}>
                      {title && <h3 className="font-heading font-extrabold text-base sm:text-lg text-white leading-tight line-clamp-2">{title}</h3>}
                      {line && <p className="text-xs text-white/80 mt-0.5 line-clamp-2">{line}</p>}
                    </motion.div>
                    <span className="inline-flex items-center gap-1 mt-2 text-[11px] font-bold text-accent">Explore <ChevronRight className="w-3.5 h-3.5" /></span>
                  </div>
                </>
              )}
            </button>
          );
        })}
      </div>
      {slides.length > 1 && (
        <div className="flex gap-1.5 justify-center">
          {slides.map((_, idx) => (
            <button key={idx} onClick={() => scrollTo(idx)} aria-label={`Slide ${idx + 1}`} className={`h-1.5 rounded-full transition-all ${idx === active ? 'bg-primary w-5' : 'bg-muted-foreground/30 w-1.5'}`} />
          ))}
        </div>
      )}
    </section>
  );
}

function Header({ eyebrow, headline, subline }) {
  if (!eyebrow && !headline) return null;
  return (
    <div className="flex items-end justify-between">
      <div>
        {eyebrow && <span className="hg-eyebrow">{eyebrow}</span>}
        {headline && <h2 className="font-heading font-extrabold text-lg sm:text-xl text-foreground">{headline}</h2>}
        {subline && <p className="text-xs text-muted-foreground mt-0.5">{subline}</p>}
      </div>
    </div>
  );
}