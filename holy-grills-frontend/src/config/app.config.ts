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
  domain: import.meta.env.VITE_SITE_URL || 'https://holy-grills.vercel.app',

  university: 'FUTA',
  currency: { code: 'NGN', symbol: '₦', locale: 'en-NG' },

  // Brand colors — mirror the `flame` scale in tailwind.config.js / src/index.css.
  themeColor: '#FF4E2D',
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

  // Native Web Push (VAPID). The public key is safe in client code — it pairs
  // with the server-side private key the backend uses to send pushes via the
  // Web Push protocol. Set this to enable the /api/push/subscribe flow.
  webPush: {
    vapidPublicKey: '', // ← Paste your VAPID public key here to enable Web Push
  },

  seo: {
    defaultTitle: "Holy Grills 🔥 — Made With More Than Flame",
    defaultDescription:
      "Made With More Than Flame. Real flame grilled chicken, wings, kebabs and crispy sides. Earn Holy Points, climb the leaderboard, unlock rewards.",
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
        "Made With More Than Flame. Real flame grilled chicken, wings and kebabs with crispy sides, delivered hot across campus.",
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
    placeId: '',
  },

  // Channel defaults — push and in-app notifications are ALWAYS delivered together.
  notifications: {
    pushAndInAppTogether: true,
  },
};

export default APP_CONFIG;