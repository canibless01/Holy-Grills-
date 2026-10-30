/**
 * Holy Grill — Central Application Configuration
 * ============================================================================
 * THE single source of truth for app-wide brand, PWA, SEO, and integration
 * constants. Every page, component, and future builder MUST import from here
 * — never hardcode the app name, currency, theme color, or brand values
 * anywhere else.
 *
 *   import APP_CONFIG from '@/config/app.config';
 *
 * See BUILDER_RULES.md for the full set of binding rules.
 * ============================================================================
 */
export const APP_CONFIG = {
  name: 'Holy Grills',
  shortName: 'HolyGrills',
  tagline: "Made With More Than Flame",
  emoji: '🔥',

  // Update to your production domain before going live (used for canonical URLs + OG).
  // Configurable per environment; the fallback is the production site. Used for
  // canonical URLs, og:url and the JSON-LD `url`.
  // Canonical/origin for og:url, canonical links and JSON-LD. Must match the
  // host actually serving the site, or search results point at a dead domain.
  // Production MUST set VITE_SITE_URL — no silent fallback to a retired domain.
  domain: import.meta.env.VITE_SITE_URL || (import.meta.env.DEV ? 'http://localhost:5173' : ''),

  university: 'FUTA',
  currency: { code: 'NGN', symbol: '₦', locale: 'en-NG' },

  // Brand colors — mirror the `flame` scale in tailwind.config.js / src/index.css.
  themeColor: '#E01616',
  backgroundColor: '#FFF5F0',
  accentColor: '#FFB400',

  pwa: {
    startUrl: '/',
    display: 'standalone',
    orientation: 'portrait',
    scope: '/',
  },

  // OneSignal web push. The App ID is a PUBLIC value (safe in client code).
  // Set it here to enable push notifications. The REST API key (server-only)
  // is stored as a secret — see holy-grills-backend/app/services/notification_service.py.
  onesignal: {
    // Push is off until an App ID is configured (VITE_ONESIGNAL_APP_ID).
    appId: import.meta.env.VITE_ONESIGNAL_APP_ID || '',
  },

  // Native Web Push (VAPID) — removed. Push delivery is OneSignal-only
  // (onesignal.appId above + the service worker importScript). webPush.ts
  // routes every "enable push" action through OneSignal.

  seo: {
    defaultTitle: "Holy Grills 🔥 — Made With More Than Flame",
    defaultDescription:
      "Holy Grills brings students together through real flame cooking, shared plates and campus experiences. Faith, love, flavour and moments that become memories.",
    ogType: 'website',
    twitterCard: 'summary_large_image',
    // Default social share image. App-relative is fine: useSEO runs it through
    // absoluteUrl() before writing og:image/twitter:image, and the pre-render
    // does the same. 1200x630 JPEG — social platforms do not render SVG.
    defaultImage: '/og-cover.jpg',

    // ── ONE global business identity, inherited by every campus ──
    // Feeds the Restaurant structured data injected on every page. Add one
    // string to `areaServed` when a new campus launches — nothing else changes.
    business: {
      type: 'Restaurant',
      description:
        "Born at FUTA in Akure, Holy Grills brings students together through real flame cooking, shared plates and campus experiences. Built on faith, love, energy and flavour, we strengthen connection and turn everyday gatherings into memories.",
      logo: '/icons/icon.svg',
      image: '',
      servesCuisine: ['Grilled Chicken', 'Fast Food', 'Nigerian'],
      priceRange: '₦₦',
      areaServed: ['FUTA, Akure'],
      telephone: '',
      address: {
        streetAddress: '',
        addressLocality: 'Akure',
        addressRegion: 'Ondo State',
        postalCode: '',
        addressCountry: 'NG',
      },
    },
  },

  // Google Business Profile — powers the post-review "Tell Google too" prompt.
  // Paste your Place ID (from your Business Profile dashboard) to deep-link
  // straight into the review form. Left empty, the prompt falls back to a
  // Google search for the business name.
  google: {
    placeId: import.meta.env.VITE_GOOGLE_BUSINESS_PLACE_ID || '',
  },

  // Channel defaults — push and in-app notifications are ALWAYS delivered together.
  notifications: {
    pushAndInAppTogether: true,
  },
};

export default APP_CONFIG;
