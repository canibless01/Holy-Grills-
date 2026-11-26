import { startTransition, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { mobilePlatform } from '@/native/devicePlatform';
import { isStandalone } from '@/lib/installPromptStore';
import { isNativeApp } from '@/native/platform';
import { loadAndroidRelease, type AndroidRelease } from '@/native/releaseManifest';
import { msg } from '@/lib/messages';

export default function AndroidDownloadCard() {
  const [platform, setPlatform] = useState<'android' | 'ios' | 'other'>('other');
  const [release, setRelease] = useState<AndroidRelease | null>(null);
  useEffect(() => {
    if (isNativeApp() || isStandalone()) return;
    const detected = mobilePlatform(); startTransition(() => setPlatform(detected));
    if (detected !== 'android') return;
    let active = true;
    loadAndroidRelease().then(value => { if (active) startTransition(() => setRelease(value)); });
    return () => { active = false; };
  }, []);
  if (platform === 'ios') return <section className="rounded-2xl bg-primary/10 border border-primary/20 p-4 flex items-center justify-between gap-4">
    <div><p className="font-bold">{msg('FE_IOS_INSTALL_TITLE', 'Holy Grills on your home screen')}</p><p className="text-sm text-muted-foreground">{msg('FE_ANDROID_DOWNLOAD_SUBTITLE', 'Your people. Your plates. One tap closer.')}</p></div>
    <button onClick={() => window.dispatchEvent(new Event('hg:install-help'))} className="shrink-0 rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground">{msg('FE_IOS_INSTALL_ACTION', 'Add to Home Screen')}</button>
  </section>;
  if (!release) return null;
  return <section className="rounded-2xl bg-primary/10 border border-primary/20 p-4 flex items-center justify-between gap-4">
    <div><p className="font-bold">{msg('FE_ANDROID_DOWNLOAD_TITLE', 'Holy Grills for Android')}</p><p className="text-sm text-muted-foreground">{msg('FE_ANDROID_DOWNLOAD_SUBTITLE', 'Your people. Your plates. One tap closer.')}</p></div>
    <Link to="/android" className="shrink-0 rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground">{msg('FE_ANDROID_DOWNLOAD_CTA', 'Download APK')}</Link>
  </section>;
}
