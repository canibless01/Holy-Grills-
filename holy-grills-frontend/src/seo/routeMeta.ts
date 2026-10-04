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
 * `title` is the PAGE-level title, exactly as passed to <SEO>; useSEO appends
 * "| <app name>" at runtime, and `headFor()` composes the same string here, so
 * the pre-rendered <title> and the title the SPA sets on navigation always
 * match. Routes whose component renders <SEO /> with no props (Home) use the
 * app defaults via `useAppDefaultTitle`.
 *
 * Copy marked "verbatim" already existed in the page before this workstream and
 * is unchanged.
 */
import APP_CONFIG from '@/config/app.config';
import { absoluteUrl } from '@/lib/seoJsonLd';

/** Canonical origin — the same value the SPA uses for canonical/og:url. */
export const SITE_ORIGIN = APP_CONFIG.domain;

export interface RouteMeta {
  /** Page-level title as passed to <SEO>; useSEO appends "| <app name>". */
  title: string;
  /** <meta name="description"> */
  description: string;
  /** Path used for the canonical URL (absolute, built from SITE_ORIGIN) */
  path: string;
  /** True when the page renders <SEO /> with no props, inheriting app defaults. */
  useAppDefaultTitle?: boolean;
  /** Absolute or app-relative social image; falls back to the template's tag */
  /** Per-route social image, overriding APP_CONFIG.seo.defaultImage. */
  image?: string;
}

export const ROUTE_META: Record<string, RouteMeta> = {
  '/': {
    title: APP_CONFIG.seo.defaultTitle,
    description: APP_CONFIG.seo.defaultDescription,
    path: '/',
    useAppDefaultTitle: true,
  },
  '/faq': {
    title: 'FAQ',
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
    title: 'Terms & Privacy',
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
      useAppDefaultTitle: true,
    }
  );
}

/** The exact <title> the SPA writes at runtime (mirrors useSEO). */
export function documentTitle(meta: RouteMeta): string {
  return meta.useAppDefaultTitle ? APP_CONFIG.seo.defaultTitle : `${meta.title} | ${APP_CONFIG.name}`;
}

/**
 * Fully resolved head data for a route — used by the pre-render, which runs no
 * effects and therefore cannot rely on useSEO to compose anything.
 */
export function headFor(path: string): { title: string; description: string; path: string; image?: string } {
  const meta = metaForPath(path);
  return {
    title: documentTitle(meta),
    description: meta.description,
    path: meta.path,
    // Always absolute: useSEO runs APP_CONFIG.seo.defaultImage through
    // absoluteUrl() too, so the static tag and the runtime tag agree.
    image: absoluteUrl(meta.image || APP_CONFIG.seo.defaultImage),
  };
}

/** The pre-rendered routes, in sitemap order. */
export const PRERENDER_ROUTES = ['/', '/faq', '/our-story', '/terms'];
