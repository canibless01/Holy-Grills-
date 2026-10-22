import { useSyncExternalStore } from 'react';

/**
 * Holy Grills mascot asset registry + celebration trigger.
 *
 * Every mascot PNG is a self-contained transparent artwork with its own
 * baked-in shadow and coloring — placements must never wrap it in a
 * backgrounded container or add CSS box/drop-shadows (see MascotStandee).
 */

// The asset host is configuration, not code: the mascots sit on the Base44 CDN
// today and are expected to move to Cloudinary. Swap VITE_ASSET_CDN_URL and every
// path below keeps working, because only the host part changes.
const CDN = (import.meta.env.VITE_ASSET_CDN_URL || 'https://media.base44.com/images/public').replace(/\/$/, '');
const BASE = `${CDN}/6aabfb4cc35dbff73aed07fe`;

// Uploaded mascot variants + the wordmark logo. Missing variants
// (shocked, savoring, openarms, bread, glove, flame) gracefully fall back
// to the closest available emotional match so placements never 404.
export const MASCOTS = {
  worried: `${BASE}/427d13814_worried.png`,
  waving: `${BASE}/fcfbfbe0d_wavingg.png`,
  thumbsup: `${BASE}/2bf2006b1_thumbsup.png`,
  peace: `${BASE}/4c77b7fd2_peacee.png`,
  cheering: `${BASE}/03a994051_cheeringg.png`,
  hips: `${BASE}/0d9731788_hips.png`,
  thinking: `${BASE}/8c21e7bc8_thinkingg.png`,
  logo: `${BASE}/5a86f3021_logoo.png`,
  // Badge "lockup" — HOLY/GRILL wordmark inside its own cream rounded
  // container. Unlike `logo` (which only sits on the site's beige background),
  // the lockup carries its own badge so it can sit on dark/colored surfaces
  // (footer gradient, admin sidebar, etc.). Never stretch — object-contain only.
  logoLockup: `${CDN}/6aac7de83bd551df4f9d0637/246a8693c_HGLockup.png`,
};

// Closest-match fallbacks for variants the asset set does not (yet) include.
const FALLBACKS = {
  shocked: 'worried',
  savoring: 'thumbsup',
  openarms: 'waving',
  bread: 'worried',
};

export function mascotUrl(name) {
  if (!name) return null;
  if (MASCOTS[name]) return MASCOTS[name];
  const fb = FALLBACKS[name];
  return fb ? MASCOTS[fb] : null;
}

// --- Mode 2 celebration store -------------------------------------------------
// A tiny external store so any page can fire a short mascot celebration
// (dim → mascot + confetti pop → fade out) without threading context.

let state: { active: boolean; mascot: unknown; key: number } = { active: false, mascot: null, key: 0 };
const listeners = new Set<(s: typeof state) => void>();
const emit = () => listeners.forEach((l) => l(state));

export function triggerMascotCelebration(mascot) {
  const url = mascotUrl(mascot);
  if (!url) return;
  state = { active: true, mascot, key: state.key + 1 };
  emit();
}

export function clearMascotCelebration() {
  if (!state.active) return;
  state = { active: false, mascot: null, key: state.key };
  emit();
}

export function useMascotCelebrationState() {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
    () => state,
  );
}