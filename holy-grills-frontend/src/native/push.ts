import { nativePushState } from './pushState';
// onesignal:managed v1 — all native OneSignal calls live in this wrapper.
import OneSignal from '@onesignal/capacitor-plugin';
import APP_CONFIG from '@/config/app.config';
import { NATIVE_ONESIGNAL_APP_ID } from './appIdentity';
import { liveApi } from '@/lib/liveApi';
import { deliverNativeRoute } from './navigation';

let init: Promise<void> | null = null;
let identity = Promise.resolve();
let desired: string | null = null;
let identified: string | null = null;
let generation = 0;
let lastDevice = '';
let deviceWrites = Promise.resolve();

async function updatePermission() {
  const allowed = await OneSignal.Notifications.hasPermission();
  nativePushState.permission = allowed ? 'granted' : await OneSignal.Notifications.canRequestPermission() ? 'default' : 'denied';
}
function syncDevice(version = generation) {
  const operation = deviceWrites.catch(() => {}).then(() => syncDeviceNow(version));
  deviceWrites = operation;
  return operation;
}
async function syncDeviceNow(version: number) {
  await updatePermission();
  const id = await OneSignal.User.pushSubscription.getIdAsync();
  const optedIn = await OneSignal.User.pushSubscription.getOptedInAsync();
  if (version !== generation || identified !== desired || !id || id.startsWith('local-') || !optedIn || nativePushState.permission !== 'granted') { nativePushState.registered = false; return; }
  if (!desired) { nativePushState.registered = true; return; }
  const key = desired + ':' + id;
  if (lastDevice !== key) {
    await liveApi.auth.deviceToken({ token: id, platform: 'android', device_model: 'Holy Grills Android' });
    if (version !== generation || identified !== desired) return;
    lastDevice = key;
  }
  nativePushState.registered = true;
}
function initialize() {
  if (init) return init;
  const appId = APP_CONFIG.onesignal.appId || NATIVE_ONESIGNAL_APP_ID;
  if (!appId) return Promise.reject(new Error('OneSignal is not configured in this Android build.'));
  init = (async () => {
    await OneSignal.initialize(appId);
    identified = await OneSignal.User.getExternalId();
    OneSignal.User.pushSubscription.addEventListener('change', () => {
      identity = identity.catch(() => {}).then(() => syncDevice()).catch(() => { nativePushState.registered = false; });
    });
    OneSignal.Notifications.addEventListener('permissionChange', () => { void updatePermission(); });
    OneSignal.Notifications.addEventListener('click', event => {
      deliverNativeRoute(event.notification.launchURL || event.result.url || (event.notification.additionalData as { action_url?: string })?.action_url);
    });
    // Web IAM campaigns are not assumed to be Android-compatible.
    OneSignal.InAppMessages.setPaused(true);
    await updatePermission();
  })().catch(error => { init = null; throw error; });
  return init;
}
export function nativePushReady(userId: string | null = null): Promise<void> {
  if (userId && userId !== desired) { desired = userId; generation++; nativePushState.registered = false; }
  const version = generation;
  identity = identity.catch(() => {}).then(async () => {
    await initialize();
    if (version !== generation) return;
    if (desired !== identified) {
      if (desired) await OneSignal.login(desired); else await OneSignal.logout();
      if (version !== generation) return;
      identified = desired;
    }
    await syncDevice(version);
  });
  return identity;
}
export async function nativePushLogout() {
  generation++; desired = null; nativePushState.registered = false; lastDevice = '';
  identity = identity.catch(() => {}).then(async () => {
    await initialize(); await OneSignal.logout(); identified = null;
    await OneSignal.Notifications.clearAll();
  });
  await identity;
}
export async function nativePushPermission() {
  await nativePushReady();
  if (!(await OneSignal.Notifications.requestPermission(true))) { await updatePermission(); return false; }
  await OneSignal.User.pushSubscription.optIn();
  const version = generation;
  const end = Date.now() + 30000;
  do {
    if (version !== generation) return false;
    await syncDevice(version);
    if (nativePushState.registered) {
      if (desired) await liveApi.notifications.updatePreferences({ push_enabled: true });
      return version === generation;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  } while (Date.now() < end);
  return false;
}
export async function nativePushOptOut() {
  generation++; nativePushState.registered = false;
  await identity.catch(() => {}); await initialize();
  const id = await OneSignal.User.pushSubscription.getIdAsync();
  await OneSignal.User.pushSubscription.optOut();
  if (desired && id) await liveApi.auth.removeDeviceToken({ token: id });
  lastDevice = '';
}
export const nativePushRegistered = () => nativePushState.registered;
export const nativePermission = () => nativePushState.permission;
