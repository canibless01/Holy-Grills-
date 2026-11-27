import { useEffect, useState } from 'react';
import { loadAndroidRelease, type AndroidRelease } from '@/native/releaseManifest';
import { msg } from '@/lib/messages';

export default function AndroidDownload() {
  const [release, setRelease] = useState<AndroidRelease | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { let active = true; loadAndroidRelease().then(value => { if (active) { setRelease(value); setLoading(false); } }); return () => { active = false; }; }, []);
  return <section className="mx-auto max-w-xl space-y-5 py-8">
    <img src="/icons/icon-192.png" alt="Holy Grills" className="h-20 w-20 rounded-2xl" />
    <h1 className="font-heading text-3xl font-extrabold">{msg('FE_ANDROID_DOWNLOAD_TITLE', 'Holy Grills for Android')}</h1>
    <p className="text-muted-foreground">{msg('FE_ANDROID_DOWNLOAD_HELP', 'Use your existing account for your menu, orders, wallet and rewards.')}</p>
    {loading ? <p role="status">{msg('FE_ANDROID_DOWNLOAD_CHECKING', 'Checking availability…')}</p> : release ? <div className="rounded-2xl border bg-card p-5 space-y-3">
      <p>{msg('FE_ANDROID_DOWNLOAD_VERSION', 'Android APK · Version {version}', { version: release.version })}</p>
      <a href={release.url} className="inline-flex rounded-full bg-primary px-6 py-3 font-bold text-primary-foreground">{msg('FE_ANDROID_DOWNLOAD_CTA', 'Download APK')}</a>
      <p className="text-sm text-muted-foreground">{msg('FE_ANDROID_DOWNLOAD_INSTALL', 'After downloading, open the APK and follow Android’s installation steps. If asked, allow installation from the browser or Files app you used.')}</p>
    </div> : <p className="rounded-2xl border bg-card p-5">{msg('FE_ANDROID_DOWNLOAD_PENDING', 'The Android app is being prepared. You can keep using Holy Grills here in your browser.')}</p>}
    <p className="text-sm">{msg('FE_ANDROID_IPHONE_HELP', 'On iPhone, open Holy Grills in Safari, tap Share, then Add to Home Screen. APK files are for Android only.')}</p>
  </section>;
}
