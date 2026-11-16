import { useEffect, useId, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Bell, Loader2, X } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { localStore } from '@/lib/storage';
import { getConsent } from '@/lib/cookieConsent';
import { ensurePushReady, isPushRegistered, isPushSupported } from '@/lib/onesignal';
import { subscribeToWebPush } from '@/lib/webPush';
import { msg } from '@/lib/messages';
import APP_CONFIG from '@/config/app.config';

const GUEST_CONSENT = 'hg_guest_push_consent_v1';
const COOLDOWN = 7 * 24 * 60 * 60 * 1000;
const AUTH_PAGES = new Set(['/login', '/register', '/signup', '/forgot-password', '/reset-password']);

/** A suggestion only: native permission is requested exclusively by the Allow tap. */
export default function PushSoftPrompt() {
  const { pathname } = useLocation();
  const { user, isLoading } = useHolyGrill();
  const { gateOpen } = useCampus();
  const userId = user?.id || null;
  const seenKey = `hg_push_prompt_v2:${userId || 'guest'}`;
  const currentKey = useRef(seenKey); currentKey.current = seenKey;
  const titleId = useId();
  const [show, setShow] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const enabling = useRef(false);
  const adopting = useRef<string | null>(null);

  useEffect(() => { setShow(false); setError(''); setBusy(false); }, [seenKey]);
  useEffect(() => {
    if (isLoading || !userId || !isPushSupported() || Notification.permission !== 'granted' || adopting.current === userId) return;
    const consentAt = Number(localStore.getItem(GUEST_CONSENT) || 0);
    if (!consentAt || Date.now() - consentAt >= COOLDOWN) return;
    adopting.current = userId;
    // Carry the guest's explicit device opt-in into the newly signed-in
    // account once. Existing account opt-outs are untouched without that tap.
    subscribeToWebPush(userId).then(ok => {
      if (currentKey.current !== seenKey) return;
      if (ok) { localStore.removeItem(GUEST_CONSENT); localStore.setItem(seenKey, String(Date.now())); }
      else { setError(msg('FE_PUSH_NOT_REGISTERED', 'Notifications are not enabled yet. Please retry.')); setShow(true); }
    }).catch(failure => { if (currentKey.current === seenKey) { setError(failure.message); setShow(true); } });
  }, [userId, isLoading, seenKey]);

  useEffect(() => {
    if (isLoading || gateOpen || AUTH_PAGES.has(pathname) || !APP_CONFIG.onesignal.appId || !isPushSupported()
        || Notification.permission !== 'default' || isPushRegistered()) return;
    if (Date.now() - Number(localStore.getItem(seenKey) || 0) < COOLDOWN) return;
    let active = true;
    const openedAt = Date.now();
    const timer = setInterval(() => {
      if (Date.now() - openedAt < 3000 || !getConsent() || document.visibilityState === 'hidden'
          || document.querySelector('[aria-modal="true"]')) return;
      clearInterval(timer);
      if (Notification.permission !== 'default' || isPushRegistered()) return;
      setShow(true); setPreparing(true);
      // Warm the existing SDK without asking permission. The Allow gesture can
      // then reach the native browser request without waiting for a CDN load.
      ensurePushReady(userId).catch(failure => { if (active) setError(failure.message); })
        .finally(() => { if (active) setPreparing(false); });
    }, 500);
    return () => { active = false; clearInterval(timer); };
  }, [seenKey, userId, pathname, isLoading, gateOpen]);

  const dismiss = () => {
    if (enabling.current) return;
    localStore.setItem(seenKey, String(Date.now())); setShow(false);
  };
  const enable = async () => {
    if (enabling.current) return;
    enabling.current = true; setBusy(true); setError('');
    const key = seenKey;
    try {
      const ok = await subscribeToWebPush(userId);
      if (currentKey.current !== key) return;
      if (ok || Notification.permission === 'denied') {
        if (ok && !userId) localStore.setItem(GUEST_CONSENT, String(Date.now()));
        if (ok && userId) localStore.removeItem(GUEST_CONSENT);
        localStore.setItem(key, String(Date.now())); setShow(false);
      } else setError(msg('FE_PUSH_NOT_REGISTERED', 'Notifications are not enabled yet. Please retry.'));
    } catch (failure) { if (currentKey.current === key) setError(failure.message || msg('FE_PUSH_SOFT_RETRY_SETTINGS', 'You can enable it later in notification settings.')); }
    finally { enabling.current = false; if (currentKey.current === key) setBusy(false); }
  };

  if (!show || gateOpen || isLoading || AUTH_PAGES.has(pathname) || !isPushSupported() || Notification.permission === 'denied') return null;
  return (
    <section role="dialog" aria-labelledby={titleId} className="fixed bottom-28 left-4 right-4 z-50 rounded-2xl border border-border bg-card p-4 shadow-xl md:bottom-5 md:left-auto md:w-96">
      <button type="button" onClick={dismiss} disabled={busy} className="absolute right-3 top-3 rounded-full p-1 hover:bg-muted disabled:opacity-50" aria-label={msg('FE_PUSH_SOFT_DISMISS', 'Dismiss')}><X className="h-4 w-4" /></button>
      <div className="flex items-start gap-3 pr-5">
        <div className="rounded-xl bg-primary/10 p-2.5"><Bell className="h-5 w-5 text-primary" /></div>
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="text-sm font-bold">{msg('FE_PUSH_SOFT_TITLE', 'Never miss an update')}</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{msg('FE_PUSH_GUEST_BODY', 'Allow Holy Grills notifications on this device. You can change this in your browser settings.')}</p>
          {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={enable} disabled={preparing || busy} className="flex items-center gap-1.5 rounded-full bg-gradient-cta px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{(preparing || busy) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{msg('FE_PUSH_ALLOW', 'Allow notifications')}</button>
            <button type="button" onClick={dismiss} disabled={busy} className="rounded-full px-3 py-2 text-xs font-bold text-muted-foreground disabled:opacity-50">{msg('FE_PUSH_SOFT_LATER', 'Maybe later')}</button>
          </div>
        </div>
      </div>
    </section>
  );
}
