import { isNativeApp } from './platform';
import { restoreNativeSession, flushNativeSession } from './secureSession';
import { deliverNativeRoute } from './navigation';
import { resumeNativePayment, clearNativePayment } from './payments';

let started = false;
export async function bootstrapNative() {
  if (!isNativeApp() || started) return;
  await restoreNativeSession();
  const { App } = await import('@capacitor/app');
  const { Browser } = await import('@capacitor/browser');
  await App.addListener('appUrlOpen', event => {
    if (deliverNativeRoute(event.url)) { clearNativePayment(); void Browser.close().catch(() => {}); }
  });
  await App.addListener('appStateChange', state => {
    if (state.isActive) resumeNativePayment(); else void flushNativeSession().catch(() => {});
  });
  await Browser.addListener('browserFinished', resumeNativePayment);
  const launch = await App.getLaunchUrl();
  if (launch?.url) { if (deliverNativeRoute(launch.url)) clearNativePayment(); } else resumeNativePayment();
  const { SplashScreen } = await import('@capacitor/splash-screen');
  await SplashScreen.hide();
  started = true;
}
