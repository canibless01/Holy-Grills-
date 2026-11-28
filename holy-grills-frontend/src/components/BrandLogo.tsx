import { MASCOTS } from '@/lib/mascots';

/**
 * Holy Grills brand logo — the uploaded wordmark PNG already contains BOTH the
 * icon and the brand name, so it is rendered on its own wherever the brand
 * appears (header, footer, auth, admin/kitchen headers). No separate "Holy
 * Grills" text label should follow it.
 *
 * `size` accepts a preset key or any explicit Tailwind sizing class string.
 * Square presets (sm/md/lg) suit the icon-only usage; the `nav`/`admin`/
 * `footer`/`auth` presets are height-constrained wordmark sizes (auto width,
 * object-contain) so the wordmark never gets squashed into a square.
 */
const SIZES = {
  sm: 'w-9 h-9',
  md: 'w-12 h-12',
  lg: 'w-14 h-14',
  // Wordmark presets — fixed height, auto width.
  nav: 'h-8 w-auto max-w-[170px]',
  admin: 'h-7 w-auto max-w-[150px]',
  footer: 'h-10 w-auto max-w-[190px]',
  auth: 'h-12 w-auto max-w-[230px]',
};

export default function BrandLogo({ size = 'sm', className = '', alt = 'Holy Grills logo', variant = 'logo' }) {
  const sizeCls = SIZES[size] || size;
  // `logo` — bare wordmark; only sits on the site's beige background.
  // `lockup` — badge wordmark with its own cream container; safe on dark/colored surfaces.
  // Both use object-contain so the artwork is never compressed or stretched.
  const src = variant === 'lockup' ? MASCOTS.logoLockup : MASCOTS.logo;
  return (
    <img
      src={src}
      alt={alt}
      draggable={false}
      className={`object-contain ${sizeCls} ${className}`}
    />
  );
}