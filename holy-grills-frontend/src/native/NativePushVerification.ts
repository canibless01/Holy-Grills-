/** NativePushVerification.ts — called by NativePushPrompt after account restoration in development builds only.
 * Debug-only, safe to keep. It observes a real subscription, never sends a test.
 * Permission remains exclusively behind the existing user-initiated Allow action.
 */
import OneSignal from '@onesignal/capacitor-plugin';
import { nativePushReady } from './push';
import { isNativeApp } from './platform';
let logged = false;
export async function installNativePushVerification() {
  if (!import.meta.env.DEV || !isNativeApp()) return;
  await nativePushReady();
  const check = async () => {
    const id = await OneSignal.User.pushSubscription.getIdAsync();
    if (!logged && id && !id.startsWith('local-') && await OneSignal.User.pushSubscription.getOptedInAsync()) {
      logged = true; console.info('[Holy Grills debug] OneSignal subscription registered:', id);
    }
  };
  OneSignal.User.pushSubscription.addEventListener('change', () => { void check(); });
  await check();
}
