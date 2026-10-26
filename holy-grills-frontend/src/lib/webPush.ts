/**
 * Holy Grill — Push enablement (OneSignal)
 * ============================================================================
 * Holy Grills sends push through OneSignal — NOT raw Web Push/VAPID. The two
 * UI entry points (PushPermissionBanner, InstallPushBonuses) call
 * `subscribeToWebPush()`; this module now routes that action through the
 * OneSignal SDK (onesignal.ts):
 *
 *   1. init OneSignal with the configured App ID (registers the OneSignal
 *      service worker and the app user).
 *   2. show OneSignal's slidedown permission prompt.
 *   3. on grant, OneSignal's subscriptionChange handler stores the player id
 *      via POST /auth/device-token (the backend owns delivery).
 *
 * The old native PushManager/VAPID implementation is gone on purpose: no
 * VAPID key exists in this product, and every surface that used to surface
 * the "set the VAPID public key" message was a dead end.
 */
import APP_CONFIG from '@/config/app.config';
import { initOneSignal, requestPushPermission, isPushSupported, optOutOneSignal } from './onesignal';

export const isWebPushSupported = isPushSupported;

/**
 * Enable push via OneSignal. Resolves true when permission was granted and
 * the device registered, false when the user dismissed the prompt.
 * Throws with a user-readable message when OneSignal isn't configured or the
 * browser blocks notifications.
 */
export const subscribeToWebPush = async () => {
  if (!APP_CONFIG.onesignal?.appId) {
    // onesignal.ts's requestPushPermission throws the same message; the guard
    // here keeps the banner from flashing a promptless state first.
    await initOneSignal(null);
  }
  // OneSignal identifies the signed-in user on its own once initOneSignal ran
  // at login (HolyGrillContext). Pass through to the slidedown prompt.
  await initOneSignal(null);
  try {
    return await requestPushPermission();
  } catch (e) {
    if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
      throw new Error('Push is blocked in your browser settings. Update site permissions to allow notifications.');
    }
    throw e;
  }
};

/**
 * Disable push on this device — flips the OneSignal subscription off. The
 * backend device-token row stays; delivery stops because OneSignal will not
 * send to an unsubscribed player.
 */
export const unsubscribeFromWebPush = async () => {
  try {
    await initOneSignal(null);
    await optOutOneSignal();
  } catch { /* non-fatal */ }
};
