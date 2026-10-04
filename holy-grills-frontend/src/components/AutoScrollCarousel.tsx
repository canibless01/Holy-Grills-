import React, { useEffect, useRef, useState, useCallback } from 'react';

/**
 * AutoScrollCarousel — a horizontal row that auto-scrolls continuously and
 * loops seamlessly, pausing on hover/touch so manual swipe works too.
 * Respects reduced-motion.
 *
 * Children must each have a fixed width + `flex-shrink-0`.
 *
 * Auto-scroll and manual swipe coexist: the rAF loop only advances scrollLeft
 * when not paused. On touch start we pause immediately; on touch end we resume
 * after a short delay so the user's swipe momentum settles first.
 *
 * The children are duplicated for a seamless infinite loop, but the duplicate
 * set gets unique keys (`dup-<key>`). Without unique keys React reconciles the
 * two sets as one, scrollWidth never reaches 2× content, and the auto-scroll
 * has nowhere to advance — so the row appears static.
 */
export default function AutoScrollCarousel({ children, speed = 30, className = '' }) {
  const ref = useRef(null);
  const [paused, setPaused] = useState(false);
  const resumeTimer = useRef(null);
  const dragState = useRef({ down: false, startX: 0, startScroll: 0 });

  const pause = useCallback(() => {
    setPaused(true);
    if (resumeTimer.current) clearTimeout(resumeTimer.current);
  }, []);

  const resume = useCallback(() => {
    if (resumeTimer.current) clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => setPaused(false), 2500);
  }, []);

  // Mouse drag-to-scroll so desktop users can "swipe" too. Touch already
  // works via native overflow scroll; only act on mouse pointers to avoid
  // fighting the native touch scroll.
  const onPointerDown = useCallback((e) => {
    if (e.pointerType !== 'mouse' || !ref.current) return;
    dragState.current = { down: true, startX: e.clientX, startScroll: ref.current.scrollLeft };
    ref.current.style.cursor = 'grabbing';
    pause();
  }, [pause]);

  const onPointerMove = useCallback((e) => {
    if (e.pointerType !== 'mouse' || !dragState.current.down || !ref.current) return;
    ref.current.scrollLeft = dragState.current.startScroll - (e.clientX - dragState.current.startX);
  }, []);

  const onPointerUp = useCallback(() => {
    if (ref.current) ref.current.style.cursor = '';
    dragState.current.down = false;
    resume();
  }, [resume]);

  useEffect(() => {
    return () => { if (resumeTimer.current) clearTimeout(resumeTimer.current); };
  }, []);

  useEffect(() => {
    if (paused) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const el = ref.current;
    if (!el) return;
    let raf;
    let last = performance.now();
    const tick = (now) => {
      const dt = now - last;
      last = now;
      el.scrollLeft += (speed * dt) / 1000;
      // Seamless loop: when we reach the end of the first set of children,
      // jump back to the start. Because children are duplicated (see below),
      // the visual content is identical so the jump is invisible.
      const half = el.scrollWidth / 2;
      if (el.scrollLeft >= half) {
        el.scrollLeft -= half;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [paused, speed]);

  // The caller supplies the duplicated content (2× the items, with unique
  // keys) so scrollWidth is genuinely 2× the visible set — that's what the
  // seamless loop below (scrollLeft -= scrollWidth/2) needs to advance and
  // reset invisibly. Duplicating inside the component with cloneElement or
  // Fragments proved unreliable (the second set was dropped from the DOM),
  // so the caller owns the duplication.
  return (
    <div
      ref={ref}
      onMouseEnter={pause}
      onMouseLeave={() => onPointerUp()}
      onTouchStart={pause}
      onTouchEnd={resume}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      className={`flex gap-3 overflow-x-auto scrollbar-hide select-none items-stretch ${paused ? 'snap-x' : ''} ${className}`}
      style={{ cursor: 'grab' }}
    >
      {children}
    </div>
  );
}