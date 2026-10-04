import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Star, ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * TestimonialSlider — an auto-rotating testimonial carousel that supports
 * manual swipe (touch + framer-motion drag), arrow controls, and pill-dot
 * tracking. Pauses on hover / while the user is interacting. Honors
 * prefers-reduced-motion.
 *
 * Shows TWO testimonials side by side on desktop (page-aligned full width) and
 * one on mobile, so it never has to stretch a single card across the page.
 *
 *   - `compact`      (default false): smaller padding + text, for item-level reviews
 *   - `subtext`      (default 'Verified Student Order'): small caption shown under the name
 *   - `testimonials`: array of `{ text, name, rating? }`. When `rating` (1–5)
 *                    is included the rendered stars reflect it, otherwise the slide
 *                    shows a fixed five-star block.
 */
export default function TestimonialSlider({ testimonials = [], intervalMs = 5500, compact = false, subtext = 'Verified Student Order' }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [perView, setPerView] = useState(1);
  const dragStartX = useRef(null);

  // Two cards on desktop, one on mobile — swipe still works on both.
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const apply = () => setPerView(mq.matches && !compact ? 2 : 1);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [compact]);

  useEffect(() => {
    if (paused || testimonials.length <= 1) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const t = setInterval(() => setI((p) => (p + 1) % testimonials.length), intervalMs);
    return () => clearInterval(t);
  }, [paused, testimonials.length, intervalMs]);

  if (testimonials.length === 0) return null;

  const next = () => setI((p) => (p + 1) % testimonials.length);
  const prev = () => setI((p) => (p - 1 + testimonials.length) % testimonials.length);

  const visible = Array.from({ length: Math.min(perView, testimonials.length) }, (_, k) => testimonials[(i + k) % testimonials.length]);

  const cardClass = compact
    ? 'rounded-menu bg-card border border-border shadow-card p-4 sm:p-5 h-full'
    : 'rounded-menu bg-card border border-border shadow-card p-5 sm:p-6 h-full';
  const textClass = compact
    ? 'font-medium text-xs sm:text-sm text-foreground italic leading-relaxed'
    : 'font-medium text-sm sm:text-base text-foreground italic leading-relaxed';
  const starSize = compact ? 'w-3 h-3' : 'w-4 h-4';
  const avatarClass = compact ? 'w-9 h-9 text-sm' : 'w-10 h-10';
  const subtextClass = compact ? 'text-[11px]' : 'text-xs';
  const userWrapClass = compact ? 'mt-3 flex items-center gap-3' : 'mt-4 flex items-center gap-3';

  return (
    <div
      className="relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={(e) => { dragStartX.current = e.touches[0].clientX; setPaused(true); }}
      onTouchEnd={(e) => {
        if (dragStartX.current != null) {
          const dx = e.changedTouches[0].clientX - dragStartX.current;
          if (Math.abs(dx) > 40) (dx < 0 ? next : prev)();
          dragStartX.current = null;
        }
        setTimeout(() => setPaused(false), 2500);
      }}
    >
      <motion.div
        key={`${i}-${perView}`}
        drag="x"
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={0.18}
        onDragEnd={(e, info) => {
          if (Math.abs(info.offset.x) > 40) (info.offset.x < 0 ? next : prev)();
        }}
        initial={{ opacity: 0, x: compact ? 12 : 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: compact ? 0.3 : 0.4, ease: 'easeOut' }}
        className={compact ? 'max-w-xl mx-auto' : ''}
      >
        <div className={`grid gap-4 ${visible.length > 1 ? 'md:grid-cols-2' : ''}`}>
          {visible.map((vm, idx) => {
            const rating = typeof vm.rating === 'number' ? vm.rating : 5;
            return (
              <div key={`${vm.name}-${idx}`} className={cardClass}>
                {/* Star rating — gold per brand (Stars / Ratings = #FFC251) */}
                <div className="flex gap-0.5 mb-2">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star key={s} className={`${starSize} ${s <= rating ? 'fill-accent text-accent' : 'text-muted'}`} />
                  ))}
                </div>
                <p className={textClass}>"{vm.text}"</p>
                <div className={userWrapClass}>
                  <div className={`rounded-full bg-gradient-cta text-white font-bold flex items-center justify-center shrink-0 ${avatarClass}`}>
                    {(vm.name || 'S').charAt(0)}
                  </div>
                  <div className="min-w-0">
                    <div className="font-heading font-bold text-sm text-foreground truncate">{vm.name}</div>
                    <div className={`${subtextClass} text-muted-foreground`}>{subtext}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>

      <div className="flex items-center justify-center gap-4 mt-4">
        <button onClick={prev} aria-label="Previous testimonial" className="w-9 h-9 rounded-lg bg-card border border-border hover:border-primary/30 hover:text-primary text-muted-foreground flex items-center justify-center transition-colors">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-1.5">
          {testimonials.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setI(idx)}
              aria-label={`Go to ${idx + 1}`}
              className={`h-2 rounded-full transition-all ${idx === i ? 'bg-primary w-5' : 'bg-muted w-2 hover:bg-muted-foreground/40'}`}
            />
          ))}
        </div>
        <button onClick={next} aria-label="Next testimonial" className="w-9 h-9 rounded-lg bg-card border border-border hover:border-primary/30 hover:text-primary text-muted-foreground flex items-center justify-center transition-colors">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}