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
/**
 * The tier fields this component reads — a structural subset of the tier payload
 * (liveApi returns it untyped, and callers pass whatever their tier hook holds,
 * so the contract here is "at least these").
 */
export interface TierIconSource {
  id?: string | number | null;
  slug?: string | null;
  name?: string | null;
  icon?: string | null;
  icon_url?: string | null;
}

interface TierIconProps {
  slug?: string;
  // Optional: callers that only know the slug still get the admin/built-in mark.
  tier?: TierIconSource;
  fallback?: string;
  className?: string;
}

export default function TierIcon({ slug, tier, fallback = '🔥', className = '' }: TierIconProps) {
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