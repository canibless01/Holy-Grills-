import { useEffect, useState } from 'react';
import { loadAndroidRelease, type AndroidRelease } from './releaseManifest';
import { msg } from '@/lib/messages';
export default function NativeUpdateNotice() {
  const [release, setRelease] = useState<AndroidRelease | null>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (Date.now() - Number(localStorage.getItem('hg_android_update_checked') || 0) < 86400000) return;
    let active = true;
    const timer = setTimeout(async () => {
      const { App } = await import('@capacitor/app'); const installed = await App.getInfo();
      if (installed.id.endsWith('.debug')) return;
      const available = await loadAndroidRelease();
      if (!active) return;
      localStorage.setItem('hg_android_update_checked', String(Date.now()));
      if (available && available.versionCode > Number(installed.build)) setRelease(available);
    }, 30000);
    return () => { active = false; clearTimeout(timer); };
  }, []);
  if (!release || hidden) return null;
  return <aside className="fixed bottom-28 left-4 right-4 z-40 rounded-2xl border bg-card p-4 shadow-xl">
    <p className="font-bold">{msg('FE_ANDROID_UPDATE_READY', 'A new Holy Grills update is ready')}</p>
    <div className="mt-3 flex gap-4"><button onClick={() => { void import('@capacitor/browser').then(({ Browser }) => Browser.open({ url: release.url })); }} className="text-primary font-bold">{msg('FE_ANDROID_UPDATE_DOWNLOAD', 'Download update')}</button><button onClick={() => setHidden(true)}>{msg('FE_PUSH_SOFT_LATER', 'Not now')}</button></div>
  </aside>;
}
