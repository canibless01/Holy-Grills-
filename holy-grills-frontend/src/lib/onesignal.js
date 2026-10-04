/**
 * Holy Grill — OneSignal Push Integration
 * ----------------------------------------------------------------------------
 * Initializes the OneSignal web SDK (only if APP_CONFIG.onesignal.appId is set),
 * maps the app user ID to OneSignal, requests push permission, and stores the
 * device token in the DeviceToken entity.
 *
 * Channel default: push + in-app are ALWAYS delivered together
 * (APP_CONFIG.notifications.pushAndInAppTogether = true).
 *
 * Call initOneSignal(userId) once after the user logs in.
 */
import APP_CONFIG from '@/config/app.config';
import { liveApi } from '@/lib/liveApi';

let initialized = false;

const loadScript = (src) =>
  new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });

const storeDeviceToken = async (userId, playerId) => {
  if (!userId || !playerId) return;
  try {
    // POST /auth/device-token — the backend owns device-token registration.
    // OneSignal gives us the player/subscription ID; the backend stores it.
    await liveApi.auth.deviceToken({
      player_id: playerId,
      platform: 'web',
      device_info: navigator.userAgent || '',
    });
  } catch (e) {
    // Token may already exist — ignore duplicate errors.
  }
};

export const initOneSignal = async (userId) => {
  const appId = APP_CONFIG.onesignal.appId;
  if (!appId || initialized) return;
  try {
    await loadScript('https://cdn.onesignal.com/sdks/OneSignalSDK.js');
    window.OneSignal = window.OneSignal || [];

    window.OneSignal.push(() => {
      window.OneSignal.init({
        appId,
        notifyButton: { enable: false },
        serviceWorkerParam: { path: '/service-worker.js', scope: '/' },
        serviceWorkerPath: 'service-worker.js',
      });
      if (userId) {
        try { window.OneSignal.setExternalUserId(userId); } catch (e) { /* ignore */ }
      }
    });

    window.OneSignal.push(() => {
      window.OneSignal.getUserId().then((playerId) => {
        if (playerId) storeDeviceToken(userId, playerId);
      });
      window.OneSignal.on('subscriptionChange', (isSubscribed) => {
        if (isSubscribed) {
          window.OneSignal.getUserId().then((playerId) => {
            if (playerId) storeDeviceToken(userId, playerId);
          });
        }
      });
    });

    initialized = true;
  } catch (e) {
    if (typeof console !== 'undefined') console.warn('[OneSignal] init failed:', e);
  }
};

export const requestPushPermission = async () => {
  const appId = APP_CONFIG.onesignal.appId;
  if (!appId) {
    // OneSignal isn't configured yet — surface the real reason instead of a
    // silent "permission denied". Push uses OneSignal (not VAPID); the App ID
    // must be set in src/config/app.config.js → onesignal.appId.
    throw new Error('Push notifications aren’t configured yet. Set the OneSignal App ID in app.config to enable them.');
  }
  if (!window.OneSignal) {
    throw new Error('OneSignal is still loading — try again in a moment.');
  }
  try {
    await window.OneSignal.push(() => window.OneSignal.showSlidedownPrompt());
    return true;
  } catch (e) {
    throw e;
  }
};

export const isPushSupported = () => {
  return typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator;
};