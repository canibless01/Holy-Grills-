import React from 'react';
import { useTierIcons } from '@/lib/tierIcons';
import { TIER_MARK_ICONS } from '@/components/TierMarkIcons';

/**
 * TierIcon — one tier mark, used everywhere a tier is shown (HP education,
 * profile menu, leaderboard, dashboard, rewards).
 *
 * Resolution order:
 *   1. an `icon_url` the backend already returned on the tier object
 *   2. the admin-uploaded tier artwork (storefront `tier_icon` section)
 *   3. the built-in inline SVG mark (ember/flame/blaze/holy) — renders
 *      consistently on every device, no CSS or font dependency
 *   4. the tier's emoji — last resort so a tier is never blank
 *
 * `className` sizes all forms (e.g. "w-8 h-8"): the image uses the box,
 * the SVG uses the box, the emoji uses the text size.
 */
export default function TierIcon({ slug, tier, fallback = '🔥', className = '' }) {
  const icons = useTierIcons();
  const key = String(slug || tier?.slug || tier?.id || '').toLowerCase();
  const url = tier?.icon_url || (key ? icons[key] : null);

  if (url) {
    return <img src={url} alt={tier?.name || key || 'Tier'} className={`object-contain ${className}`} />;
  }

  const SvgIcon = TIER_MARK_ICONS[key];
  if (SvgIcon) {
    return <SvgIcon className={className} />;
  }

  return <span className={className}>{tier?.icon || fallback}</span>;
}