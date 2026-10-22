import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { msg } from '@/lib/messages';
import { openCmsDestination } from '@/lib/safeNavigation';

export type CompactBannerSlide = { image?: string; tag?: string; sub?: string; cta?: string; cta_url?: string; display_mode?: 'image' | 'text' };

/** Same compact slot for complete artwork or a real icon/copy/action row. */
export default function CompactBannerCarousel({ slides }: { slides: CompactBannerSlide[] }) {
  const navigate = useNavigate();
  const rail = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const reducedMotion = useReducedMotion();
  useEffect(() => { setActive(0); rail.current?.scrollTo({ left: 0 }); }, [slides]);
  const advance = (index: number) => {
    rail.current?.scrollTo({ left: index * rail.current.clientWidth, behavior: reducedMotion ? 'auto' : 'smooth' });
    setActive(index);
  };
  useEffect(() => {
    if (slides.length < 2 || paused || reducedMotion) return;
    const timer = setInterval(() => setActive(previous => {
      const next = (previous + 1) % slides.length;
      rail.current?.scrollTo({ left: next * rail.current.clientWidth, behavior: 'smooth' });
      return next;
    }), 4500);
    return () => clearInterval(timer);
  }, [slides.length, paused, reducedMotion]);
  if (!slides.length) return null;
  return <section aria-label={msg('FE_COMPACT_BANNER_LABEL', 'Promotions')} className="relative rounded-2xl overflow-hidden border border-border bg-card"
    onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onTouchStart={() => setPaused(true)} onTouchEnd={() => setPaused(false)}
    onFocusCapture={() => setPaused(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false); }}>
    <div ref={rail} className="flex overflow-x-auto scrollbar-hide snap-x snap-mandatory" onScroll={() => {
      if (rail.current?.clientWidth) setActive(Math.round(rail.current.scrollLeft / rail.current.clientWidth));
    }}>
      {slides.map((slide, index) => {
        const action = () => { if (slide.cta_url) openCmsDestination(slide.cta_url, navigate); };
        const artwork = slide.display_mode !== 'text';
        return <div key={index} className="w-full min-w-full shrink-0 snap-start" style={{ height: 'clamp(104px, 25vw, 160px)' }}>
          {artwork ? <button type="button" onClick={action} disabled={!slide.cta_url} aria-label={slide.tag || msg('FE_MENU_BANNER_OPEN', 'Open banner')} className="block w-full h-full disabled:cursor-default">
            <img src={slide.image} alt={slide.tag || ''} className="w-full h-full object-contain" loading={index ? 'lazy' : 'eager'} />
          </button> : <div className="h-full flex items-center gap-3 px-4 py-3 pb-5">
            {slide.image && <img src={slide.image} alt="" className="w-11 h-11 sm:w-14 sm:h-14 shrink-0 object-contain" />}
            <div className="min-w-0 flex-1">
              {slide.tag && <h3 className="font-bold text-sm sm:text-base text-foreground line-clamp-2">{slide.tag}</h3>}
              {slide.sub && <p className="text-xs sm:text-sm text-muted-foreground mt-1 line-clamp-2">{slide.sub}</p>}
            </div>
            {slide.cta && slide.cta_url && <button type="button" onClick={action} className="shrink-0 rounded-full border border-primary px-3 py-1.5 text-xs font-bold text-primary hover:bg-primary/10">{slide.cta}</button>}
          </div>}
        </div>;
      })}
    </div>
    {slides.length > 1 && <div className="absolute bottom-2 inset-x-0 flex justify-center gap-1">
      {slides.map((_, index) => <button key={index} type="button" onClick={() => advance(index)} aria-label={msg('FE_CMS_GO_TO_SLIDE', 'Go to slide {number}', { number: index + 1 })} aria-current={index === active ? 'true' : undefined} className={`h-1.5 rounded-full ${index === active ? 'w-4 bg-primary' : 'w-1.5 bg-muted-foreground/35'}`} />)}
    </div>}
  </section>;
}
