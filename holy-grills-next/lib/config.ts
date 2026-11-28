/** Pilot-only adapter. Keep aligned with src/config/app.config.ts until shared-config extraction. */
export const APP_CONFIG = {
  name: 'Holy Grills',
  tagline: 'Made With More Than Flame',
  description: 'Connect with campus life at FUTA, Akure. Discover flame-grilled meals, shared experiences, student events and Holy Points with Holy Grills.',
  currency: {code: 'NGN', locale: 'en-NG'},
  liveOrigin: new URL(process.env.LIVE_SITE_URL || 'https://holygrills.online').origin,
} as const;
export const money = (amount: number) => new Intl.NumberFormat(APP_CONFIG.currency.locale, {
  style: 'currency', currency: APP_CONFIG.currency.code, maximumFractionDigits: 0,
}).format(amount);
