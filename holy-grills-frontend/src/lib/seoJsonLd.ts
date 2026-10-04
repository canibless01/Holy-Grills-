/**
 * Holy Grill — SEO structured data (JSON-LD) builders
 * ----------------------------------------------------------------------------
 * ONE global business identity (APP_CONFIG.seo.business) is shared by every
 * campus — nothing campus-specific lives here. When a new campus launches, add
 * one string to `business.areaServed`.
 *
 *   restaurantJsonLd()  → injected on EVERY page (see useSEO)
 *   menuItemJsonLd(item) → injected ONLY on an individual menu item page
 */
import APP_CONFIG from '@/config/app.config';

/** Turn a possibly-relative asset path into an absolute URL for crawlers. */
export const absoluteUrl = (url) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${APP_CONFIG.domain}${url.startsWith('/') ? '' : '/'}${url}`;
};

/** The global Restaurant block — same on every page, every campus. */
/** Shape of APP_CONFIG.seo.business (app.config.js) as used below. */
interface SeoBusiness {
  type?: string;
  logo?: string;
  image?: string;
  description?: string;
  servesCuisine?: string[];
  priceRange?: string;
  areaServed?: string[];
  telephone?: string;
  address?: Record<string, unknown>;
}

export const restaurantJsonLd = () => {
  const b: SeoBusiness = APP_CONFIG.seo.business || {};
  const logo = absoluteUrl(b.logo);
  const image = absoluteUrl(b.image);
  return {
    '@context': 'https://schema.org',
    '@type': b.type || 'Restaurant',
    name: APP_CONFIG.name,
    url: APP_CONFIG.domain,
    description: b.description || APP_CONFIG.seo.defaultDescription,
    ...(logo ? { logo } : {}),
    ...(image ? { image } : {}),
    ...(b.servesCuisine?.length ? { servesCuisine: b.servesCuisine } : {}),
    ...(b.priceRange ? { priceRange: b.priceRange } : {}),
    ...(b.areaServed?.length ? { areaServed: b.areaServed } : {}),
    ...(b.telephone ? { telephone: b.telephone } : {}),
    ...(b.address ? { address: { '@type': 'PostalAddress', ...b.address } } : {}),
  };
};

/** Per-item block — the only place individual menu data enters structured data. */
export const menuItemJsonLd = (item) => {
  if (!item) return null;
  const img = absoluteUrl(item.image_url);
  return {
    '@context': 'https://schema.org',
    '@type': 'MenuItem',
    name: item.name,
    ...(item.description ? { description: item.description } : {}),
    ...(img ? { image: img } : {}),
    offers: {
      '@type': 'Offer',
      price: item.price,
      priceCurrency: APP_CONFIG.currency.code,
      availability: item.is_sold_out || item.is_available === false
        ? 'https://schema.org/OutOfStock'
        : 'https://schema.org/InStock',
    },
  };
};