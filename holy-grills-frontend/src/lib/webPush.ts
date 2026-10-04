/**
 * Holy Grill — Native Web Push Subscription
 * ============================================================================
 * Aligns with the backend's /api/push/subscribe (POST/DELETE) routes in
 * notifications.py (push_bp). The backend stores a standard browser
 * PushSubscription object ({ endpoint, keys: { p256dh, auth } }) in the
 * push_subscriptions table.
 *
 * This is SEPARATE from the OneSignal flow (onesignal.js → /auth/device-token).
 * Both coexist — the backend's notification service sends via whichever
 * subscription a device has. Use this module when the backend's Web Push
 * route is the intended delivery channel.
 *
 * Requires a VAPID public key in APP_CONFIG.webPush.vapidPublicKey.
 */
import APP_CONFIG from '@/config/app.config';
import { liveApi } from './liveApi';
import { msg } from '@/lib/messages';

/**
 * Convert a base64 string to a Uint8Array for pushManager.subscribe().
 * The VAPID public key from the backend is base64url-encoded.
 */
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    output[i] = rawData.charCodeAt(i);
  }
  return output;
}

export const isWebPushSupported = () => {
  return typeof window !== 'undefined'
    && 'serviceWorker' in navigator
    && 'PushManager' in window
    && 'Notification' in window;
};

/**
 * Subscribe the browser to Web Push and register the subscription with the
 * backend (POST /push/subscribe). Returns true on success.
 *
 * Flow:
 *   1. Request Notification permission (if not already granted).
 *   2. Subscribe via pushManager.subscribe({ userVisibleOnly: true, applicationServerKey }).
 *   3. POST the subscription object to /push/subscribe with a device label.
 *   4. POST the same subscription to /challenges/push-subscribed, which claims the
 *      push-subscribe milestone / PWA-push bonus (it 404s when the milestone is not
 *      configured, so its failure never blocks registration).
 */
export const subscribeToWebPush = async () => {
  const vapidKey = APP_CONFIG.webPush?.vapidPublicKey;
  if (!vapidKey) {
    throw new Error(
      msg('FE_WEB_PUSH_WEB_PUSH_ISN_T_CONFIGURED_YET_SET_THE', 'Web Push isn’t configured yet. Set the VAPID public key in app.config → webPush.vapidPublicKey to enable it.')
    );
  }
  if (!isWebPushSupported()) {
    throw new Error(msg('FE_WEB_PUSH_THIS_BROWSER_DOESN_T_SUPPORT_WEB_PUSH', 'This browser doesn’t support Web Push notifications.'));
  }

  // Step 1 — permission
  if (Notification.permission === 'denied') {
    throw new Error(msg('FE_WEB_PUSH_PUSH_IS_BLOCKED_IN_YOUR_BROWSER', 'Push is blocked in your browser settings. Update site permissions to allow notifications.'));
  }
  if (Notification.permission !== 'granted') {
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') {
      return false;
    }
  }

  // Step 2 — PushSubscription
  const reg = await navigator.serviceWorker.ready;
  let subscription = await reg.pushManager.getSubscription();
  if (!subscription) {
    subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey),
    });
  }

  // Step 3 — register with backend
  const subJSON = subscription.toJSON();
  const deviceLabel = navigator.userAgent || 'Web browser';
  await liveApi.push.subscribe({ subscription: subJSON, device_label: deviceLabel });

  // Reward path: /challenges/push-subscribed stores the same subscription AND
  // awards the push milestone / PWA-push bonus. Kept non-blocking — enabling push
  // must succeed even where the milestone is not configured.
  await liveApi.challenges.pushSubscribed({ subscription: subJSON, device_label: deviceLabel }).catch(() => {});

  return true;
};

/**
 * Unsubscribe the browser from Web Push — both locally (PushSubscription.unsubscribe)
 * and on the backend (DELETE /push/subscribe). Pass an optional endpoint to
 * unsubscribe a single device; omit to deactivate all of the user's subscriptions.
 */
export const unsubscribeFromWebPush = async (endpoint) => {
  if (isWebPushSupported()) {
    try {
      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.getSubscription();
      if (subscription) {
        endpoint = endpoint || subscription.endpoint;
        await subscription.unsubscribe();
      }
    } catch { /* local unsubscribe failure is non-fatal */ }
  }
  await liveApi.push.unsubscribe(endpoint ? { endpoint } : {});
};