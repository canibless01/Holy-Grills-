/**
 * Holy Grill — OneSignal Push Integration (v16 User-Model SDK)
 * ----------------------------------------------------------------------------
 * Initializes the OneSignal v16 web SDK (only if APP_CONFIG.onesignal.appId is
 * set), identifies the user via OneSignal.login(), requests push permission,
 * and stores the push subscription ID in the DeviceToken entity.
 *
 * v16 changes from legacy:
 *   • SDK URL: OneSignalSDK.page.js (not OneSignalSDK.js)
 *   • Queue: OneSignalDeferred (not OneSignal.push)
 *   • Identity: OneSignal.login(userId) / OneSignal.logout()
 *   • Subscription: OneSignal.User.PushSubscription.id (not getUserId)
 *   • Events: addEventListener('change') (not .on('subscriptionChange'))
 *   • Permission: OneSignal.Notifications.requestPermission()
 *
 * Channel default: push + in-app are ALWAYS delivered together
 * (APP_CONFIG.notifications.pushAndInAppTogether = true).
 *
 * Call initOneSignal(userId) once after the user logs in.
 * Call logoutOneSignal() when the user signs out.
 */
import APP_CONFIG from '@/config/app.config';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';

// v16 SDK type — the page SDK exposes OneSignalDeferred as a global queue.
declare global {
  interface Window {
    OneSignalDeferred?: Array<(OneSignal: any) => Promise<void> | void>;
  }
}

// v16 SDK entry point — the page SDK, not the legacy bundle.
const ONESIGNAL_SDK_URL = 'https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js';

let initialized = false;
let sdkInstance: any = null;
let registeredUserId: string | null = null;

const loadScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });

const storeDeviceToken = async (userId: string, subscriptionId: string) => {
  if (!userId || !subscriptionId) return;
  await liveApi.auth.deviceToken({
    player_id: subscriptionId,
    platform: 'web',
    device_info: navigator.userAgent || '',
  });
};

export const initOneSignal = async (userId: string) => {
  const appId = APP_CONFIG.onesignal.appId;
  if (userId) registeredUserId = userId;
  if (!appId) return;

  // Already initialised — just re-login the new user (e.g. account switch).
  if (initialized) {
    if (userId && sdkInstance) {
      try { await sdkInstance.login(userId); } catch (e) { /* ignore */ }
    }
    return;
  }

  try {
    await loadScript(ONESIGNAL_SDK_URL);

    // v16 uses OneSignalDeferred — the page SDK passes the live instance
    // into the callback so we can call init(), login(), etc. directly.
    window.OneSignalDeferred = window.OneSignalDeferred || [];

    await new Promise<void>((resolve) => {
      window.OneSignalDeferred!.push(async (OneSignal) => {
        try {
          await OneSignal.init({
            appId,
            serviceWorkerPath: 'service-worker.js',
            serviceWorkerParam: { scope: '/' },
            notifyButton: { enable: false },
          });

          sdkInstance = OneSignal;
          initialized = true;

          // Identify the signed-in user (sets external_id alias).
          if (userId) {
            try { await OneSignal.login(userId); } catch (e) { /* ignore */ }
          }

          // Store the push subscription ID when it becomes available.
          const currentId = OneSignal.User?.PushSubscription?.id;
          if (currentId) storeDeviceToken(registeredUserId!, currentId).catch(() => {});

          // Re-store whenever the subscription changes (new token, re-subscribe, etc.).
          OneSignal.User?.PushSubscription?.addEventListener('change', (event: any) => {
            const subId = event?.current?.id;
            if (subId && registeredUserId) {
              storeDeviceToken(registeredUserId, subId).catch(() => {});
            }
          });
        } catch (initError) {
          // init() can fail (network, invalid appId, blocked by ad-blocker, etc.).
          // Always resolve the outer promise so callers do not hang.
          if (typeof console !== 'undefined') console.warn('[OneSignal] init failed:', initError);
        } finally {
          resolve();
        }
      });
    });
  } catch (e) {
    if (typeof console !== 'undefined') console.warn('[OneSignal] load failed:', e);
  }
};

/**
 * Unlink the current user from the push subscription on sign-out.
 * v16: OneSignal.logout() removes the external_id and resets to anonymous.
 */
export const logoutOneSignal = async () => {
  registeredUserId = null;
  if (sdkInstance) {
    try { await sdkInstance.logout(); } catch (e) { /* ignore */ }
  }
};

export const requestPushPermission = async () => {
  const appId = APP_CONFIG.onesignal.appId;
  if (!appId) {
    // OneSignal isn't configured yet — surface the real reason instead of a
    // silent "permission denied". Push uses OneSignal (not VAPID); the App ID
    // must be set in src/config/app.config.js → onesignal.appId.
    throw new Error(msg('FE_ONESIGNAL_PUSH_NOTIFICATIONS_AREN_T_CONFIGURED', 'Push notifications aren\u2019t configured yet. Set the OneSignal App ID in app.config to enable them.'));
  }
  if (!sdkInstance) {
    throw new Error(msg('FE_ONESIGNAL_ONE_SIGNAL_IS_STILL_LOADING_TRY_AGAIN', 'OneSignal is still loading \u2014 try again in a moment.'));
  }

  return new Promise<boolean>((resolve, reject) => {
    const sdk = sdkInstance;
    const userId = registeredUserId;
    let settled = false;
    let checking = false;

    const finish = (value: boolean, error: any = null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      clearInterval(poll);
      try {
        sdk.Notifications?.removeEventListener('permissionChange', onPermissionChange);
        sdk.User?.PushSubscription?.removeEventListener('change', onSubChange);
      } catch { /* ignore */ }
      if (error) reject(error); else resolve(value);
    };

    const checkSubscribed = async (): Promise<boolean> => {
      const optedIn = sdk.User?.PushSubscription?.optedIn;
      const subId = sdk.User?.PushSubscription?.id;
      if (optedIn && subId && userId && registeredUserId === userId) {
        await storeDeviceToken(userId, subId);
        return true;
      }
      return false;
    };

    const verify = async () => {
      if (settled || checking) return;
      checking = true;
      try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
          finish(false); return;
        }
        const granted = await checkSubscribed();
        if (granted) finish(true);
      } catch (failure) { finish(false, failure); }
      finally { checking = false; }
    };

    const onPermissionChange = (permission: boolean) => { if (permission) verify(); };
    const onSubChange = () => { verify(); };

    // Opening the prompt does not mean the browser granted permission.
    const timeout = setTimeout(() => finish(false), 45000);
    const poll = setInterval(verify, 1500);

    try {
      sdk.Notifications?.addEventListener('permissionChange', onPermissionChange);
      sdk.User?.PushSubscription?.addEventListener('change', onSubChange);
    } catch { /* ignore */ }

    (async () => {
      try {
        await verify();
        if (settled) return;
        // v16: native browser prompt via the Notifications namespace.
        await sdk.Notifications?.requestPermission();
        await verify();
      } catch (failure) { finish(false, failure); }
    })();
  });
};

export const isPushSupported = () => {
  return typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator;
};
