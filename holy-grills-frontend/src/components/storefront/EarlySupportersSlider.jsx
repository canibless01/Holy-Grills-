import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ExternalLink, Heart } from 'lucide-react';
import { getEarlySupporters } from '@/lib/storefrontMockData';

// Compact supporter cards — small square photo on top, name + note + social
// link below in a clean bordered card. No gradient overlays; cards are small
// enough that multiple fit on screen without dominating the page.
export default function EarlySupportersSlider({ eyebrow = 'Since day one', headline = 'The First Believers 💛', subline = 'They ordered before anyone else did.' }) {
  const [supporters, setSupporters] = useState(null);
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    let live = true;
    getEarlySupporters()
      .then((list) => { if (live) setSupporters(Array.isArray(list) ? list : []); })
      .catch(() => { if (live) setSupporters([]); });
    return () => { live = false; };
  }, []);

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

  useEffect(() => {
    if (!supporters || supporters.length <= 1 || reducedMotion || paused) return;
    const timer = setInterval(() => {
      setActive((p) => {
        const next = (p + 1) % supporters.length;
        const el = scrollRef.current;
        if (el && el.children[next]) el.scrollTo({ left: el.children[next].offsetLeft, behavior: 'smooth' });
        return next;
      });
    }, 4500);
    return () => clearInterval(timer);
  }, [supporters, reducedMotion, paused]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !supporters || supporters.length <= 1) return;
    const idx = Math.round(el.scrollLeft / (el.children[0]?.offsetWidth || 1));
    if (idx !== active && idx >= 0 && idx < supporters.length) setActive(idx);
  }, [supporters, active]);

  if (!supporters) {
    return (
      <section className="space-y-3">
        <Header eyebrow={eyebrow} headline={headline} subline={subline} />
        <div className="flex gap-3 overflow-hidden">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-2xl bg-card border border-border animate-pulse w-[150px] sm:w-[calc((100%-2rem)/3)]" style={{ height: 200 }} />
          ))}
        </div>
      </section>
    );
  }
  if (supporters.length === 0) return null;

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
        {supporters.map((s, i) => {
          const content = s.content || {};
          const name = s.name || content.name || s.title || 'Supporter';
          const note = s.note || content.note || s.subtitle || '';
          const photo = s.photo_url || content.photo_url || content.photo || '';
          const social = s.social_links || content.social_links || '';
          const socialUrl = typeof social === 'string' ? social : (social?.url || social?.link || '');
          return (
            <div
              key={s.id || i}
              className="shrink-0 snap-start w-[150px] sm:w-[calc((100%-2rem)/3)]"
              style={{ scrollSnapAlign: 'start' }}
            >
              <div className="rounded-2xl bg-card border border-border overflow-hidden">
                <div className="relative aspect-square bg-secondary overflow-hidden">
                  {photo ? (
                    <img src={photo} alt={name} loading={i < 3 ? 'eager' : 'lazy'} decoding="async" className="absolute inset-0 w-full h-full object-cover" />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center"><Heart className="w-8 h-8 text-muted-foreground/30" /></div>
                  )}
                </div>
                <div className="p-2.5">
                  <h3 className="font-heading font-bold text-xs text-foreground truncate leading-tight">{name}</h3>
                  {note && <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2 leading-snug">{note}</p>}
                  {socialUrl && (
                    <a href={socialUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 mt-1.5 text-[10px] font-bold text-primary">
                      <ExternalLink className="w-3 h-3" /> Follow
                    </a>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {supporters.length > 1 && (
        <div className="flex gap-1.5 justify-center">
          {supporters.map((_, idx) => (
            <button key={idx} onClick={() => scrollTo(idx)} aria-label={`Supporter ${idx + 1}`} className={`h-1.5 rounded-full transition-all ${idx === active ? 'bg-primary w-5' : 'bg-muted-foreground/30 w-1.5'}`} />
          ))}
        </div>
      )}
    </section>
  );
}

function Header({ eyebrow, headline, subline }) {
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