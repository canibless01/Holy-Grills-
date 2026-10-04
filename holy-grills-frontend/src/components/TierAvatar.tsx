import React from 'react';
import { getTierAccent } from '@/lib/hgUtils';

/**
 * TierAvatar — the profile picture wrapped in a tier ring.
 *
 * The ring is the tier signal (like a "premium account" halo): it travels with
 * the member's face everywhere they appear — header, profile menu, profile page.
 *
 * The ladder is deliberate. Every tier shares one geometry, so the shapes read
 * as the same object growing hotter rather than four unrelated decorations:
 *   ember — soft bare band, flat, no glow. You haven't earned a halo yet.
 *   flame — warm matte band, flat, no glow. The first real colour.
 *   blaze — bright saturated band, flat, no glow.
 *   holy  — thicker band of living gold, shimmering, the only glowing ring.
 *
 * Band widths and classes are literal strings from fixed maps so Tailwind's
 * scanner always sees them and nothing is built at runtime.
 */
const RINGS = {
  ember: { ring: 'tier-ring-ember', band: { sm: 'p-[1.5px]', md: 'p-[2px]', lg: 'p-[2.5px]' } },
  flame: { ring: 'tier-ring-flame', band: { sm: 'p-[2px]', md: 'p-[2.5px]', lg: 'p-[3px]' } },
  blaze: { ring: 'tier-ring-blaze', band: { sm: 'p-[2.5px]', md: 'p-[3px]', lg: 'p-[3.5px]' } },
  holy: { ring: 'tier-ring-holy', band: { sm: 'p-[3px]', md: 'p-[3.5px]', lg: 'p-[4px]' } },
};

const SIZES = {
  sm: { gap: 'p-[2px]', inner: 'w-7 h-7 text-[11px]' },
  md: { gap: 'p-[2.5px]', inner: 'w-10 h-10 text-sm' },
  lg: { gap: 'p-[3px]', inner: 'w-16 h-16 text-2xl' },
};

export default function TierAvatar({ user, hpEarned120Day = 0, size = 'md', className = '' }) {
  const accent = getTierAccent(hpEarned120Day);
  const s = SIZES[size] || SIZES.md;
  const band = RINGS[accent.slug] || RINGS.ember;
  const avatarUrl = user?.avatar_url || user?.profile?.avatar_url;

  return (
    <span
      className={`inline-flex shrink-0 rounded-full ${band.ring} ${band.band[size] || band.band.md} ${className}`}
      title={accent.icon}
    >
      <span className={`inline-flex rounded-full bg-card ${s.gap}`}>
        <span className={`flex items-center justify-center overflow-hidden rounded-full bg-gradient-cta font-extrabold text-white ${s.inner}`}>
          {avatarUrl ? (
            <img src={avatarUrl} alt={user?.full_name || 'Profile picture'} className="w-full h-full object-cover" />
          ) : (
            user?.full_name?.charAt(0)?.toUpperCase() || '?'
          )}
        </span>
      </span>
    </span>
  );
}