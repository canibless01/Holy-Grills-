import { useEffect, useState } from 'react';
import { loadAndroidRelease, type AndroidRelease } from './releaseManifest';
import { msg } from '@/lib/messages';
import { createUpdateCheck } from './updateChecks';
export default function NativeUpdateNotice() {
  const [release, setRelease] = useState<AndroidRelease | null>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    let active = true, handle: { remove: () => Promise<void> } | undefined;
    const checker = createUpdateCheck({
      getInfo: async () => (await import('@capacitor/app')).App.getInfo(),
      load: loadAndroidRelease,
      lastSuccess: () => Number(localStorage.getItem('hg_android_update_checked') || 0),
      markSuccess: time => localStorage.setItem('hg_android_update_checked', String(time)),
      onUpdate: available => { setRelease(available); setHidden(false); },
    });
    const timer = setTimeout(() => { void checker.check(); }, 30000);
    void import('@capacitor/app').then(async ({ App }) => {
      handle = await App.addListener('appStateChange', state => { if (state.isActive) void checker.check(); });
      if (!active) await handle.remove();
    }).catch(() => {});
    return () => { active = false; clearTimeout(timer); checker.stop(); void handle?.remove(); };
  }, []);
  if (!release || hidden) return null;
  return <aside className="fixed bottom-28 left-4 right-4 z-40 rounded-2xl border bg-card p-4 shadow-xl">
    <p className="font-bold">{msg('FE_ANDROID_UPDATE_READY', 'A new Holy Grills update is ready')}</p>
    <div className="mt-3 flex gap-4"><button onClick={() => { void import('@capacitor/browser').then(({ Browser }) => Browser.open({ url: release.url })); }} className="text-primary font-bold">{msg('FE_ANDROID_UPDATE_DOWNLOAD', 'Download update')}</button><button onClick={() => setHidden(true)}>{msg('FE_PUSH_SOFT_LATER', 'Not now')}</button></div>
  </aside>;
}
