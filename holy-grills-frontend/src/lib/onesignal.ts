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
let identifiedUserId: string | null = null;
let storedDevice: { userId: string; subscriptionId: string } | null = null;
let initialization: Promise<void> | null = null;
let identityGeneration = 0;
let identityTask: { userId: string; promise: Promise<void> } | null = null;
const SDK_TIMEOUT_MS = 15000;

const loadScript = (src: string) => new Promise<void>((resolve, reject) => {
  if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
  const script = document.createElement('script');
  script.src = src; script.async = true; script.defer = true;
  script.onload = () => resolve();
  script.onerror = () => { script.remove(); reject(new Error('push_sdk_unavailable')); };
  document.head.appendChild(script);
});

const storeDeviceToken = async (userId: string, subscriptionId: string) => {
  if (!userId || !subscriptionId || registeredUserId !== userId || identifiedUserId !== userId) return;
  await liveApi.auth.deviceToken({ token: subscriptionId, platform: 'web', device_model: (navigator.userAgent || '').slice(0, 100) });
  if (registeredUserId === userId && identifiedUserId === userId) storedDevice = { userId, subscriptionId };
};

const initialize = async (appId: string) => {
  let timer: ReturnType<typeof setTimeout>;
  try {
    await Promise.race([
      (async () => {
        await loadScript(ONESIGNAL_SDK_URL);
        window.OneSignalDeferred = window.OneSignalDeferred || [];
        await new Promise<void>((resolve, reject) => {
          window.OneSignalDeferred!.push(async (OneSignal) => {
            try {
              await OneSignal.init({
                appId, serviceWorkerPath: 'service-worker.js', serviceWorkerParam: { scope: '/' },
                notifyButton: { enable: false },
                promptOptions: { slidedown: { prompts: [{ type: 'push', autoPrompt: false }] } },
              });
              sdkInstance = OneSignal;
              initialized = true;
              OneSignal.User?.PushSubscription?.addEventListener('change', (event: any) => {
                const id = event?.current?.id;
                if (id && registeredUserId && identifiedUserId === registeredUserId) {
                  storeDeviceToken(registeredUserId, id).catch(() => {});
                }
              });
              resolve();
            } catch (error) { reject(error); }
          });
        });
      })(),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('push_sdk_timeout')), SDK_TIMEOUT_MS); }),
    ]);
  } finally { clearTimeout(timer!); }
};

export const initOneSignal = async (userId: string | null) => {
  const appId = APP_CONFIG.onesignal.appId;
  if (userId) registeredUserId = userId;
  if (!appId || !registeredUserId) return;
  try {
    if (!initialized) {
      if (!initialization) initialization = initialize(appId).finally(() => { initialization = null; });
      await initialization;
    }
    const target = registeredUserId;
    if (target && identifiedUserId !== target) {
      if (identityTask?.userId === target) { await identityTask.promise; return; }
      const previous = identityTask?.promise;
      const version = ++identityGeneration;
      const promise = (async () => {
        await previous?.catch(() => {});
        if (version !== identityGeneration || registeredUserId !== target) return;
        await sdkInstance.login(target);
        if (version !== identityGeneration || registeredUserId !== target) return;
        identifiedUserId = target;
        const id = sdkInstance.User?.PushSubscription?.id;
        if (id) await storeDeviceToken(target, id);
      })();
      identityTask = { userId: target, promise };
      try { await promise; } finally { if (identityTask?.promise === promise) identityTask = null; }
    }
  } catch {
    // Optional push initialization never blocks account restoration. The
    // explicit enable action reports missing readiness and can be retried.
  }
};

export const optOutOneSignal = async () => {
  if (sdkInstance) await sdkInstance.User?.PushSubscription?.optOut();
};

/**
 * Unlink the current user from the push subscription on sign-out.
 * v16: OneSignal.logout() removes the external_id and resets to anonymous.
 */
export const logoutOneSignal = async () => {
  registeredUserId = null; identifiedUserId = null; storedDevice = null; identityGeneration += 1;
  if (sdkInstance) {
    await identityTask?.promise.catch(() => {});
    try { await sdkInstance.logout(); } catch (e) { /* ignore */ }
  }
};

export const requestPushPermission = async () => {
  const appId = APP_CONFIG.onesignal.appId;
  if (!appId) {
    // OneSignal isn't configured yet — surface the real reason instead of a
    // silent "permission denied". Push uses OneSignal (not VAPID); the App ID
    // must be set in src/config/app.config.js → onesignal.appId.
    throw new Error(msg('FE_ONESIGNAL_PUSH_NOTIFICATIONS_AREN_T_CONFIGURED', 'Push notifications aren’t configured yet. Set the OneSignal App ID in app.config to enable them.'));
  }
  if (!sdkInstance || !registeredUserId || identifiedUserId !== registeredUserId) {
    throw new Error(msg('FE_ONESIGNAL_ONE_SIGNAL_IS_STILL_LOADING_TRY_AGAIN', 'OneSignal is still loading — try again in a moment.'));
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
      if (optedIn && subId && userId && registeredUserId === userId && identifiedUserId === userId) {
        await storeDeviceToken(userId, subId);
        if (registeredUserId !== userId || identifiedUserId !== userId) return false;
        await liveApi.notifications.updatePreferences({ push_enabled: true });
        if (registeredUserId !== userId || identifiedUserId !== userId) return false;
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
        if (typeof Notification === 'undefined' || Notification.permission !== 'granted') await sdk.Notifications?.requestPermission();
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') await sdk.User?.PushSubscription?.optIn();
        await verify();
      } catch (failure) { finish(false, failure); }
    })();
  });
};

export const isPushSupported = () => {
  return typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator;
};

export const isPushRegistered = () => Boolean(storedDevice && registeredUserId &&
  storedDevice.userId === registeredUserId && identifiedUserId === registeredUserId &&
  sdkInstance?.User?.PushSubscription?.optedIn && sdkInstance?.User?.PushSubscription?.id === storedDevice.subscriptionId);
