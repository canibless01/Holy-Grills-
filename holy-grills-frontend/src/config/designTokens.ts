/**
 * Holy Grill — Design Tokens (JS mirror)
 * ============================================================================
 * Mirrors the CSS custom properties in src/index.css so JS code (charts, canvas,
 * inline styles, animation configs) can reference the exact same values.
 *
 * CSS (src/index.css) is the PRIMARY source for styling. This file is the
 * JS-accessible mirror — keep the two in sync when a value changes.
 *
 *   import { COLORS, RADIUS, SHADOWS, Z_INDEX } from '@/config/designTokens';
 * ============================================================================
 */
export const COLORS = {
  flame: {
    50: '#FFF5F0', 100: '#FFE6D9', 200: '#FFCDB5', 300: '#FFA578',
    400: '#FF9500', 500: '#FF6B1A', 600: '#FF4E2D', 700: '#D63D20',
    800: '#A8301A', 900: '#7A2313',
  },
  cocoa: {
    50: '#F9F5EF', 100: '#F0E8DC', 200: '#E1D1BD', 300: '#C9AC91',
    400: '#9C7042', 500: '#6B4A2E', 600: '#5A3D26', 700: '#462719',
    800: '#321B11', 900: '#1F100A',
  },
  primary: '#FF4E2D',
  accent: '#FFB400',
  success: '#16A34A',
  warning: '#F59E0B',
  error: '#DC2626',
  neutral: '#6B7280',
  background: '#FFF8F2',
  foreground: '#321B11',
};

// 4px base scale — use these for consistent spacing in JS layouts.
export const SPACING = {
  0: 0, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, '2xl': 32, '3xl': 48, '4xl': 64,
};

export const RADIUS = {
  none: '0', sm: '0.5rem', md: '0.75rem', lg: '1rem', xl: '1.5rem', '2xl': '2rem',
  pill: '9999px', circle: '50%',
};

export const SHADOWS = {
  sm: '0 1px 2px rgba(50,27,17,0.06)',
  md: '0 4px 12px rgba(50,27,17,0.08)',
  lg: '0 8px 24px rgba(50,27,17,0.12)',
  xl: '0 16px 40px rgba(50,27,17,0.16)',
  flame: '0 8px 24px rgba(255,78,45,0.30)',
};

// Layering system — never invent z-index values inline; use this scale.
export const Z_INDEX = {
  base: 0,
  dropdown: 1000,
  sticky: 1020,
  overlay: 1040,
  modal: 1060,
  toast: 1080,
  tooltip: 1100,
};

export const BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280, '2xl': 1536 };

export const FONTS = {
  heading: 'Sora',
  body: 'Inter',
  display: 'Sora',
  mono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
};

// Animation timing tokens — use for framer-motion transitions & CSS transitions.
export const ANIMATION = {
  fast: '150ms',
  normal: '300ms',
  slow: '500ms',
  slower: '800ms',
  easeOut: [0.16, 1, 0.3, 1], // expo-out — buttery
  spring: { type: 'spring', stiffness: 380, damping: 30 },
};

// Tier ring colors (profile photo ring per tier).
export const TIER_RING_COLORS = {
  Ember: '#FF9500',
  Flame: '#FF6B1A',
  Blaze: '#FFD700',
  Holy: 'gold', // animated gold shimmer — handled in CSS
};