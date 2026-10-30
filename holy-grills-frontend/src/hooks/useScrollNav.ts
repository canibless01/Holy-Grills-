import { useState, useEffect } from 'react';

/**
 * Scroll-aware navigation — hides the top/bottom nav when the user scrolls
 * down, reveals it the moment they scroll back up. Shared by TopNav and
 * BottomNav so the whole app behaves one way.
 *
 * - Always visible near the top of the page (scrollY <= 10).
 * - Always visible near the bottom of the page (within ~120px of the end),
 *   so the bar reappears once you've reached the last section even though
 *   you were scrolling down to get there — no dead strip at the foot.
 * - A small direction threshold avoids jitter on tiny scrolls.
 */
export function useScrollNav() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const y = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const nearBottom = docHeight > 0 && y + 120 >= docHeight;
        if (y <= 10) setVisible(true);
        else if (nearBottom) setVisible(true);
        else if (y > lastY + 6) setVisible(false);
        else if (y + 6 < lastY) setVisible(true);
        lastY = y;
        ticking = false;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return visible;
}