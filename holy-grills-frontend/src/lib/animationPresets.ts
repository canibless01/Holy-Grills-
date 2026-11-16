/**
 * Holy Grill — Animation Presets (framer-motion variants)
 * ============================================================================
 * Reusable motion variants for every micro-interaction in the spec.
 * Import and spread into <motion.*> components:
 *
 *   import { fadeUp, staggerContainer } from '@/lib/animationPresets';
 *   <motion.div variants={staggerContainer()} initial="hidden" animate="show">
 *     <motion.div variants={fadeUp}>...</motion.div>
 *   </motion.div>
 *
 * Principle: "If the moment matters, amplify it. If it's routine, keep it quiet."
 * Navigation/filtering/reading = smooth + invisible. Earning HP, tier upgrades,
 * badge unlocks, spin wins, rank rises = amplified.
 *
 * Respects prefers-reduced-motion via the <ReduceMotion /> guard in App.
 * ============================================================================
 */
import { ANIMATION } from '@/config/designTokens';

const EASE = ANIMATION.easeOut;

// ── Page / list entrance ──
export const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.3, ease: EASE } },
};

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.9 },
  show: { opacity: 1, scale: 1, transition: { duration: 0.3, ease: EASE } },
};

export const staggerContainer = (stagger = 0.05, delay = 0) => ({
  hidden: {},
  show: { transition: { staggerChildren: stagger, delayChildren: delay } },
});

// ── Cart interactions ──
export const cartAddPop = {
  hidden: { scale: 1 },
  show: { scale: [1, 1.15, 1], transition: { duration: 0.3, ease: EASE } },
};

export const cartIconBounce = {
  rest: { scale: 1 },
  bump: { scale: [1, 1.25, 1], transition: { duration: 0.3, ease: EASE } },
};

export const cartRemoveFade = {
  hidden: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.8, transition: { duration: 0.2, ease: EASE } },
};

// ── HP balance count-up (number rolls like a slot digit) ──
export const hpCountUp = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 1.5, ease: EASE } },
};

// ── Badge unlock: face-down flip + shimmer + bounce ──
export const badgeUnlock = {
  hidden: { rotateY: 180, opacity: 0, scale: 0.8 },
  show: {
    rotateY: 0, opacity: 1, scale: 1,
    transition: { duration: 0.5, ease: EASE },
  },
  bounce: { scale: [1, 1.1, 1], transition: { duration: 0.4, ease: EASE, delay: 0.5 } },
};

// ── Tier upgrade: full-screen moment ──
export const tierUpgrade = {
  hidden: { opacity: 0, scale: 0.5 },
  show: {
    opacity: 1, scale: 1,
    transition: { duration: 0.6, ease: EASE, type: 'spring', stiffness: 200, damping: 18 },
  },
  glow: {
    boxShadow: [
      '0 0 0px rgba(255,215,0,0)',
      '0 0 40px rgba(255,215,0,0.6)',
      '0 0 0px rgba(255,215,0,0)',
    ],
    transition: { duration: 1.2, repeat: Infinity, ease: 'easeInOut' },
  },
};

// ── Spin wheel ──
export const spinWheelIdle = {
  animate: { rotate: 360, transition: { duration: 8, ease: 'linear', repeat: Infinity } },
};

export const spinWheelSegment = {
  win: { scale: [1, 1.08, 1], transition: { duration: 0.4, ease: EASE, repeat: 2 } },
};

// ── Leaderboard: sequential slide-in + gold pulse on user's row ──
export const leaderboardRow = (index) => ({
  hidden: { opacity: 0, x: -20 },
  show: { opacity: 1, x: 0, transition: { duration: 0.3, ease: EASE, delay: index * 0.05 } },
});

export const leaderboardSelfPulse = {
  animate: { boxShadow: ['0 0 0px rgba(255,215,0,0)', '0 0 16px rgba(255,215,0,0.5)', '0 0 0px rgba(255,215,0,0)'], transition: { duration: 1.5, repeat: Infinity, ease: 'easeInOut' } },
};

// ── Streak flame grows with each day; pulses at 7 ──
export const streakFlame = (days) => ({
  animate: {
    scale: days >= 7 ? [1, 1.15, 1] : 1,
    transition: days >= 7 ? { duration: 1, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.3 },
  },
});

// ── Tier progress: liquid fill (not a sliding bar) ──
export const liquidFill = (progress) => ({
  initial: { height: '0%' },
  animate: { height: `${progress}%`, transition: { duration: 1, ease: EASE } },
});

// ── HP transfer: outgoing swoosh / incoming chime ──
export const transferOut = {
  hidden: { opacity: 1, x: 0, scale: 1 },
  exit: { opacity: 0, x: 60, scale: 0.6, transition: { duration: 0.4, ease: EASE } },
};

export const transferIn = {
  hidden: { opacity: 0, x: -60, scale: 0.6 },
  show: { opacity: 1, x: 0, scale: 1, transition: { duration: 0.4, ease: EASE } },
};

// ── Notification banner slide-in from top ──
export const bannerSlideDown = {
  hidden: { opacity: 0, y: -24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE } },
  exit: { opacity: 0, y: -24, transition: { duration: 0.2, ease: EASE } },
};

// ── Reduced-motion-safe wrapper: pass variants, get static fallback ──
export const reducedMotion = {
  hidden: { opacity: 1 },
  show: { opacity: 1, transition: { duration: 0.01 } },
};