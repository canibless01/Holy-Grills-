import { useResumeEffect } from '@/hooks/useResumeEffect';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useReducedMotion } from 'framer-motion';
import { Pause, Play } from 'lucide-react';
import { getStorefrontSections } from '@/lib/storefrontMockData';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import { useNavigate } from 'react-router-dom';
import { openCmsDestination } from '@/lib/safeNavigation';
import { bannerSpec, storefrontSpecId } from '@/lib/bannerSpec';
import BannerCard from './BannerCard';

// One card shell for every storefront row — the frame (shape + suggested design
// size) comes from lib/bannerSpec so the admin help text and the rendered card
// can never disagree.
//   compact   → What's Inside (row cards, 3:1 artwork frame)
//   banner    → Promos on the menu page (row cards, 4:1 artwork strip)
//   landscape → How It's Made (stacked cards, 3:2 picture)
//   poster    → Promos on home/checkout (stacked cards, 3:2 picture)
const VARIANTS = {
  banner: { cardClass: 'w-full', maxW: undefined },
  compact: { cardClass: 'w-full', maxW: undefined },
  landscape: { cardClass: 'w-[80vw] sm:w-[calc((100%-0.75rem)/2)]', maxW: 440 },
  poster: { cardClass: 'w-[80vw] sm:w-[calc((100%-0.75rem)/2)]', maxW: 440 },
  portrait: { cardClass: 'w-[68vw] sm:w-[calc((100%-1.5rem)/3)]', maxW: 300 },
};

export default function StorefrontSlider({ sectionType, variant = 'poster', eyebrow = '', headline = '', subline = '', placement = 'home' }) {
  const navigate = useNavigate();
  const { campusId } = useCampus();
  const [slides, setSlides] = useState(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [userPaused, setUserPaused] = useState(false);
  const [focusWithin, setFocusWithin] = useState(false);
  const reducedMotion = useReducedMotion();
  const scrollRef = useRef(null);

  const v = VARIANTS[variant] || VARIANTS.poster;
  const spec = bannerSpec(storefrontSpecId(variant));

  useResumeEffect((background) => {
    let live = true;
    if (!background) { setSlides(null); setActive(0); }
    getStorefrontSections(sectionType)
      .then((list) => {
        if (!live) return;
        const arr = (Array.isArray(list) ? list : [])
          .filter((s) => s.is_active !== false && (!s.content?.placement || s.content.placement === placement))
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        setSlides(arr);
      })
      .catch(() => { if (live && !background) setSlides([]); });
    return () => { live = false; };
  }, [sectionType, campusId, placement]);

  const scrollTo = useCallback((idx) => {
    const el = scrollRef.current;
    if (!el) return;
    const card = el.children[idx];
    if (card) el.scrollTo({ left: card.offsetLeft - (el.children[0]?.offsetLeft || 0), behavior: reducedMotion ? 'auto' : 'smooth' });
    setActive(idx);
  }, [reducedMotion]);

  // Auto-advance + loop. The `paused` flag stops/restarts the interval cleanly —
  // no manual timer juggling. Stays still for reduced-motion users.
  useEffect(() => {
    if (!slides || slides.length <= 1 || reducedMotion || paused || userPaused || focusWithin) return;
    const timer = setInterval(() => {
      setActive((p) => {
        const next = (p + 1) % slides.length;
        const el = scrollRef.current;
        if (el && el.children[next]) el.scrollTo({ left: el.children[next].offsetLeft - (el.children[0]?.offsetLeft || 0), behavior: reducedMotion ? 'auto' : 'smooth' });
        return next;
      });
    }, 4500);
    return () => clearInterval(timer);
  }, [slides, reducedMotion, paused, userPaused, focusWithin]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !slides || slides.length <= 1) return;
    const idx = Math.round(el.scrollLeft / ((el.children[0]?.offsetWidth || 1) + 12));
    if (idx !== active && idx >= 0 && idx < slides.length) setActive(idx);
  }, [slides, active]);

  // What's Inside is a guest-only pitch ("The perks behind the login"), so its
  // action defaults to the sign-up page. A CMS row that sets its own
  // destination or label still wins — nothing is hardcoded for other sections.
  const guestAction = sectionType === 'whats_inside';
  const defaultDestination = guestAction ? '/register' : '';
  const defaultActionLabel = guestAction ? msg('FE_SF_SIGN_UP', 'Sign up') : '';

  const destinationOf = (slide) => (
    slide.content?.cta_url || slide.content?.cta_link || slide.cta_url || slide.content?.destination || defaultDestination
  );

  const handleTap = (slide) => {
    // Section rows keep cta_url inside `content` (aliased to cta_link); the
    // legacy `destination` key is still honoured last.
    const dest = destinationOf(slide);
    if (!dest) return;
    // Route guards enforce authentication only where the destination needs it.
    openCmsDestination(dest, navigate);
  };

  if (!slides) {
    return (
      <section className="space-y-3">
        <Header eyebrow={eyebrow} headline={headline} subline={subline} />
        <div className="flex gap-3 overflow-hidden">
          {[0, 1, 2].map((i) => (
            <div key={i} className={`rounded-2xl bg-card border border-border animate-pulse ${v.cardClass}`} style={{ aspectRatio: spec.aspect, maxWidth: v.maxW }} />
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
        onFocusCapture={() => setFocusWithin(true)}
        onBlurCapture={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setFocusWithin(false); }}
        onTouchStart={() => setPaused(true)}
        onTouchEnd={() => setPaused(false)}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        className="flex items-start gap-3 overflow-x-auto scrollbar-hide snap-x snap-mandatory -mx-1 px-1"
        style={{ scrollSnapType: 'x mandatory' }}
      >
        {slides.map((s, i) => {
          const img = s.image_url || s.content?.image_url || '';
          const title = s.title || s.content?.title || '';
          const line = s.subtitle || s.content?.line || s.content?.subtitle || '';
          // Artwork-only sections carry no extra copy: the design is the message.
          const artworkOnly = s.content?.display_mode === 'image' || (variant === 'banner' && !s.content?.display_mode);
          const destination = artworkOnly ? '' : destinationOf(s);
          const actionLabel = artworkOnly ? '' : (
            s.content?.cta_text || s.cta_text || defaultActionLabel || (destination ? msg('FE_STOREFRONT_EXPLORE', 'Explore') : '')
          );
          const label = artworkOnly
            ? (title || msg('FE_MENU_BANNER_OPEN', 'Open banner'))
            : (title && actionLabel ? `${title} — ${actionLabel}` : (title || msg('FE_STOREFRONT_EXPLORE', 'Explore')));
          return (
            <BannerCard
              key={s.id || i}
              spec={spec}
              mode={artworkOnly ? 'artwork' : 'text'}
              image={img}
              title={title}
              line={line}
              eyebrow={s.content?.eyebrow || ''}
              badge={s.content?.badge || s.badge || ''}
              actionLabel={actionLabel}
              label={label}
              onAction={artworkOnly
                ? (s.content?.cta_url || s.content?.cta_link || s.cta_url || s.content?.destination ? () => handleTap(s) : undefined)
                : (destination ? () => handleTap(s) : undefined)}
              eager={i < 3}
              className={`shrink-0 snap-start ${v.cardClass}`}
              style={{ maxWidth: v.maxW, scrollSnapAlign: 'start' }}
            />
          );
        })}
      </div>
      {slides.length > 1 && (
        <div className="flex gap-1.5 justify-center items-center">
          {!reducedMotion && <button type="button" onClick={() => setUserPaused(!userPaused)} aria-label={userPaused ? msg('FE_SF_PLAY', 'Resume carousel') : msg('FE_SF_PAUSE', 'Pause carousel')} className="p-2 rounded-full text-muted-foreground hover:bg-muted">{userPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}</button>}
          {slides.map((_, idx) => (
            <button key={idx} onClick={() => scrollTo(idx)} aria-label={msg('FE_CMS_SLIDE_NUMBER', 'Slide {number}', { number: idx + 1 })} aria-current={idx === active ? 'true' : undefined} className={`h-1.5 rounded-full transition-all ${idx === active ? 'bg-primary w-5' : 'bg-muted-foreground/30 w-1.5'}`} />
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
