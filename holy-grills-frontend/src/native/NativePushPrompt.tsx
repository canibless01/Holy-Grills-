import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { nativePushReady, nativePushRegistered, nativePermission, nativePushPermission } from './push';
import { msg } from '@/lib/messages';

export default function NativePushPrompt() {
  const { user, isLoading } = useHolyGrill();
  const { gateOpen } = useCampus();
  const { pathname } = useLocation();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = `hg_native_push_prompt:${user?.id || 'guest'}`;
  useEffect(() => {
    setShow(false);
    if (isLoading || gateOpen || ['/login', '/register', '/signup', '/forgot-password', '/reset-password'].includes(pathname)) return;
    let active = true;
    const timer = setTimeout(() => {
      nativePushReady(user?.id || null).then(() => {
        if (import.meta.env.DEV) import('./NativePushVerification').then(module => module.installNativePushVerification()).catch(() => {});
        if (active && !nativePushRegistered() && nativePermission() !== 'denied' && Date.now() - Number(localStorage.getItem(key) || 0) > 7 * 86400000) setShow(true);
      }).catch(() => {}); // Optional push must never block browsing or account creation.
    }, 3000);
    return () => { active = false; clearTimeout(timer); };
  }, [user?.id, isLoading, gateOpen, pathname, key]);
  if (!show || gateOpen) return null;
  return <section role="dialog" aria-label={msg('FE_PUSH_SOFT_TITLE', 'Stay close to the fire')} className="fixed bottom-28 left-4 right-4 z-50 rounded-2xl border bg-card p-4 shadow-xl">
    <p className="font-bold">{msg('FE_PUSH_SOFT_TITLE', 'Stay close to the fire')}</p>
    <p className="mt-2 text-sm">{msg('FE_PUSH_SOFT_BODY', 'Get order updates and a little campus goodness. You choose when to allow notifications.')}</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <div className="mt-3 flex gap-4"><button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { const ok = await nativePushPermission(); if (ok || nativePermission() === 'denied') { localStorage.setItem(key, String(Date.now())); setShow(false); } else setError(msg('FE_PUSH_NOT_REGISTERED', 'Notifications are not enabled yet. Please retry.')); } catch { setError(msg('FE_PUSH_NOT_REGISTERED', 'Notifications are not enabled yet. Please retry.')); } finally { setBusy(false); } }} className="rounded-full bg-primary px-5 py-2 font-bold text-primary-foreground">{msg('FE_PUSH_SOFT_ENABLE', 'Allow notifications')}</button>
      <button disabled={busy} onClick={() => { localStorage.setItem(key, String(Date.now())); setShow(false); }}>{msg('FE_PUSH_SOFT_LATER', 'Not now')}</button></div>
  </section>;
}
