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
  brand: {
    introduction: 'Holy Grills is a student ecosystem built around connection and participation in campus life. We started with flame-grilled food at FUTA in Akure, bringing students together over shared meals. Today, food, campus events and Holy Points give students more ways to discover what is happening and be part of it.',
    mission: 'To strengthen the connections between students, each other and campus life by making it easier to discover, participate and find value in the experiences around them.',
    vision: 'A connected campus network where students, local businesses and event organisers can find each other, share opportunities and make campus life more rewarding to be part of.',
  },
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
    defaultTitle: "Holy Grills — Food, Events & Campus Life at FUTA, Akure",
    defaultDescription:
      "Connect with campus life at FUTA, Akure. Discover flame-grilled meals, shared experiences, student events and Holy Points with Holy Grills.",
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
        "Holy Grills is a student ecosystem connecting students with each other and campus life, starting at the Federal University of Technology Akure (FUTA), Ondo State, Nigeria. Flame-grilled chicken, wings, skewers, plates, buns and shared meals bring people together. Campus events and Holy Points create more reasons to discover, participate and return. Food is the everyday starting point; connection is the purpose. Made With More Than Flame. Faith. Love. Energy. Flavor.",
      profileUrl: 'https://g.page/r/CT3sD6yYtneQECA',
      mapUrl: 'https://www.google.com/maps?cid=10409989830528199741',
      logo: '/icons/icon.svg',
      image: '',
      servesCuisine: ['Grilled Chicken', 'Fast Food', 'Nigerian'],
      priceRange: '₦₦',
      areaServed: ['Federal University of Technology Akure (FUTA)', 'Akure, Ondo State, Nigeria'],
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

  // Google's “Ask for reviews” link works without a Places API/billing setup.
  // A Place ID remains an optional alternative for existing configurations.
  google: {
    reviewUrl: import.meta.env.VITE_GOOGLE_REVIEW_URL || 'https://g.page/r/CT3sD6yYtneQECA/review',
    placeId: import.meta.env.VITE_GOOGLE_BUSINESS_PLACE_ID || '',
  },

  // Channel defaults — push and in-app notifications are ALWAYS delivered together.
  notifications: {
    pushAndInAppTogether: true,
  },
};

export default APP_CONFIG;
