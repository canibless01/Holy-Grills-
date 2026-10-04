import { useState, useEffect, useRef } from 'react';

/**
 * Animates a number from its previous value to `target` over `duration` ms
 * using an easeOutCubic curve. Re-runs whenever `target` changes, continuing
 * from the current displayed value so live updates (wallet top-up, HP earn)
 * count up from where the user last saw it, not from 0.
 */
export function useCountUp(target, duration = 1000) {
  const [value, setValue] = useState(0);
  const fromRef = useRef(0);
  const rafRef = useRef(null);
  useEffect(() => {
    const from = fromRef.current;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
      else { setValue(target); fromRef.current = target; }
    };
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);
  return value;
}