/**
 * Per-route SEO metadata (Track B)
 * ============================================================================
 * ONE source of truth for the head of every pre-rendered public route.
 *
 *   - the build-time pre-render (`scripts/prerender.mjs`) writes these tags
 *     into the static HTML, so a crawler that never runs JS still sees them;
 *   - the page component passes the same object to <SEO>, so the live SPA
 *     updates the title/description/canonical identically when a visitor
 *     navigates client-side.
 *
 * Values marked "verbatim" were already in the page before this workstream and
 * are copied unchanged. Routes without an entry fall back to APP_CONFIG.seo
 * defaults, exactly as they already do at runtime.
 */
import APP_CONFIG from '@/config/app.config';

export interface RouteMeta {
  /** <title> — also used for og:title / twitter:title */
  title: string;
  /** <meta name="description"> */
  description: string;
  /** Path used for the canonical URL (absolute, built from APP_CONFIG.domain) */
  path: string;
  /** Absolute or app-relative social image; falls back to APP_CONFIG.seo.defaultImage */
  image?: string;
}

export const ROUTE_META: Record<string, RouteMeta> = {
  '/': {
    title: APP_CONFIG.seo.defaultTitle,
    description: APP_CONFIG.seo.defaultDescription,
    path: '/',
  },
  '/faq': {
    title: 'FAQ — Holy Grills',
    description:
      'Answers about ordering, delivery across FUTA, Holy Points, payments, squad orders and refunds at Holy Grills.',
    path: '/faq',
  },
  '/our-story': {
    // verbatim from src/pages/OurStory.tsx
    title: 'Holy Grills: The Student Flame Grill Built at FUTA, Akure',
    description:
      "Holy Grills is FUTA's student focused flame grill in Akure. Real open flame, campus delivery, Holy Points and a community that shows up together.",
    path: '/our-story',
  },
  '/terms': {
    title: 'Terms & Privacy — Holy Grills',
    description:
      'The terms of service and privacy policy for ordering from Holy Grills: accounts, payments, delivery, refunds and how we handle your data.',
    path: '/terms',
  },
};

/** Metadata for a path, falling back to the app-wide SEO defaults. */
export function metaForPath(path: string): RouteMeta {
  return (
    ROUTE_META[path] || {
      title: APP_CONFIG.seo.defaultTitle,
      description: APP_CONFIG.seo.defaultDescription,
      path,
    }
  );
}

/** The pre-rendered routes, in sitemap order. */
export const PRERENDER_ROUTES = ['/', '/faq', '/our-story', '/terms'];
