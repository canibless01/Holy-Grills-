import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { msg } from '@/lib/messages';
import { openCmsDestination } from '@/lib/safeNavigation';
import { bannerSpec } from '@/lib/bannerSpec';
import BannerCard from './BannerCard';

export type CompactBannerSlide = {
  image?: string;
  mobileImage?: string;
  tag?: string;
  sub?: string;
  cta?: string;
  cta_url?: string;
  display_mode?: 'image' | 'text';
};

/**
 * Banner rail for the menu, checkout and homepage banner placements. Every
 * slide renders through BannerCard, so a banner is the same rounded frame as a
 * What's Inside card: complete artwork fills the frame edge to edge, or an
 * icon/photo sits inset beside its copy and CTA button.
 */
export default function CompactBannerCarousel({ slides, spec = 'strip' }: { slides: CompactBannerSlide[]; spec?: 'strip' | 'wide' }) {
  const navigate = useNavigate();
  const rail = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const reducedMotion = useReducedMotion();
  const frame = bannerSpec(spec);

  useEffect(() => { setActive(0); rail.current?.scrollTo({ left: 0 }); }, [slides]);

  const advance = (index: number) => {
    rail.current?.scrollTo({ left: index * rail.current.clientWidth, behavior: reducedMotion ? 'auto' : 'smooth' });
    setActive(index);
  };

  useEffect(() => {
    if (slides.length < 2 || paused || reducedMotion) return;
    const timer = setInterval(() => setActive((previous) => {
      const next = (previous + 1) % slides.length;
      rail.current?.scrollTo({ left: next * rail.current.clientWidth, behavior: 'smooth' });
      return next;
    }), 4500);
    return () => clearInterval(timer);
  }, [slides.length, paused, reducedMotion]);

  if (!slides.length) return null;

  return (
    <section
      aria-label={msg('FE_COMPACT_BANNER_LABEL', 'Promotions')}
      className="relative rounded-2xl overflow-hidden border border-border bg-card"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={() => setPaused(true)}
      onTouchEnd={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false); }}
    >
      <div
        ref={rail}
        className="flex overflow-x-auto scrollbar-hide snap-x snap-mandatory"
        onScroll={() => {
          if (rail.current?.clientWidth) setActive(Math.round(rail.current.scrollLeft / rail.current.clientWidth));
        }}
      >
        {slides.map((slide, index) => {
          const artworkOnly = slide.display_mode !== 'text';
          const destination = slide.cta_url || '';
          const action = destination ? () => openCmsDestination(destination, navigate) : undefined;
          const actionLabel = artworkOnly ? '' : (slide.cta || (destination ? msg('FE_STOREFRONT_EXPLORE', 'Explore') : ''));
          return (
            <div key={index} className="w-full min-w-full shrink-0 snap-start">
              <BannerCard
                spec={frame}
                mode={artworkOnly ? 'artwork' : 'text'}
                image={slide.image || ''}
                title={slide.tag || ''}
                line={slide.sub || ''}
                actionLabel={actionLabel}
                label={slide.tag || msg('FE_MENU_BANNER_OPEN', 'Open banner')}
                onAction={action}
                eager={index === 0}
                className="rounded-none border-0"
              />
            </div>
          );
        })}
      </div>
      {slides.length > 1 && (
        <div className="absolute bottom-2 inset-x-0 flex justify-center gap-1">
          {slides.map((_, index) => (
            <button
              key={index}
              type="button"
              onClick={() => advance(index)}
              aria-label={msg('FE_CMS_GO_TO_SLIDE', 'Go to slide {number}', { number: index + 1 })}
              aria-current={index === active ? 'true' : undefined}
              className={`h-1.5 rounded-full ${index === active ? 'w-4 bg-primary' : 'w-1.5 bg-muted-foreground/35'}`}
            />
          ))}
        </div>
      )}
    </section>
  );
}
