
/**
 * TierMarkIcons — four inline SVG tier marks (ember / flame / blaze / holy).
 *
 * Replaces the emoji fallbacks (🔥 🕯️ 💥 👑) that render inconsistently
 * across devices. Each SVG inherits `currentColor` so it tints to the tier
 * color via the parent's text-* class. `className` sizes the SVG box.
 */

// Ember — a single flame (the spark tier)
export function EmberIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C12 2 8 6 8 11C8 13 9 14 10 14C10 14 9 12 10 10C11 8 12 7 12 7C12 9 13 10 14.5 11.5C16 13 17 14.5 17 16.5C17 19.5 14.8 22 12 22C8.5 22 6 19.5 6 16C6 12 8 9 9 7C9.5 6 10 5 10 4C10.5 5 11 5.5 12 2Z" fill="currentColor"/>
    </svg>
  );
}

// Flame — a candle with a lit wick (the steady tier)
export function CandleIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      {/* Flame */}
      <path d="M12 2C12 2 10 4 10 6C10 7.5 11 8 12 8C13 8 14 7.5 14 6C14 4 12 2 12 2Z" fill="currentColor"/>
      {/* Wick */}
      <line x1="12" y1="8" x2="12" y2="10" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
      {/* Candle body */}
      <rect x="8" y="10" width="8" height="11" rx="1.5" fill="currentColor" fillOpacity="0.85"/>
      {/* Wax drip detail */}
      <path d="M8 14C8 14 7 15 7 16.5C7 17.5 7.5 18 8 18" stroke="currentColor" strokeWidth="0.8" fill="none" opacity="0.5"/>
    </svg>
  );
}

// Blaze — a burst / explosion (the hot tier)
export function BlastIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      {/* Center burst */}
      <path d="M12 2L13.5 8L19 6L15 11L22 12L15 13L19 18L13.5 16L12 22L10.5 16L5 18L9 13L2 12L9 11L5 6L10.5 8L12 2Z" fill="currentColor"/>
    </svg>
  );
}

// Holy — a crown (the top tier)
export function CrownIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M3 7L6 17H18L21 7L17 11L12 4L7 11L3 7Z" fill="currentColor"/>
      <rect x="6" y="18" width="12" height="2.5" rx="1" fill="currentColor"/>
      <circle cx="3" cy="7" r="1.5" fill="currentColor"/>
      <circle cx="21" cy="7" r="1.5" fill="currentColor"/>
      <circle cx="12" cy="4" r="1.5" fill="currentColor"/>
    </svg>
  );
}

// Map tier slug → SVG component
export const TIER_MARK_ICONS = {
  ember: EmberIcon,
  flame: CandleIcon,
  blaze: BlastIcon,
  holy: CrownIcon,
};