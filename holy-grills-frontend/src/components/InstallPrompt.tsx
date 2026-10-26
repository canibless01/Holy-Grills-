/**
 * Holy Grill — PWA Install Prompt
 * ----------------------------------------------------------------------------
 * Custom install banner (Android/Chrome) + iOS-specific instructions modal.
 * Listens for `beforeinstallprompt`, shows a dismissible banner, and triggers
 * the native prompt. On iOS (no beforeinstallprompt) shows a "Add to Home
 * Screen" instruction sheet.
 *
 * Rendered once at the app root (App.tsx) — covers every page automatically.
 */
import { useEffect, useState } from 'react';
import { Download, X, Share2, Plus, Flame } from 'lucide-react';
import ModalPortal from '@/components/ModalPortal';
import { hasInstallPrompt, isStandalone, triggerInstall, subscribeInstallPrompt } from '@/lib/installPromptStore';
import { localStore } from '@/lib/storage';
import { msg, useMessages } from '@/lib/messages';

const DISMISS_KEY = 'hg_install_dismissed';

export default function InstallPrompt() {
  useMessages();
  const [show, setShow] = useState(false);
  const [showIOS, setShowIOS] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const isIOS = typeof navigator !== 'undefined' && (/iphone|ipad|ipod/i.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1));
  const recentlyDismissed = () => {
    const saved = Number(localStore.getItem(DISMISS_KEY));
    return saved > 1 && Date.now() >= saved && Date.now() - saved < 7 * 86400000;
  };
  useEffect(() => {
    const update = () => setShow(!isStandalone() && hasInstallPrompt() && !recentlyDismissed());
    const manual = () => {
      if (isStandalone()) return;
      setError(false);
      if (hasInstallPrompt()) setShow(true);
      else setShowIOS(true);
    };
    const installed = () => { setShow(false); setShowIOS(false); };
    update();
    const unsubscribe = subscribeInstallPrompt(update);
    window.addEventListener('hg:install-help', manual);
    window.addEventListener('appinstalled', installed);
    return () => {
      unsubscribe();
      window.removeEventListener('hg:install-help', manual);
      window.removeEventListener('appinstalled', installed);
    };
  }, []);

  useEffect(() => {
    if (!isIOS || isStandalone() || recentlyDismissed()) return;
    const timer = setTimeout(() => setShowIOS(true), 4000);
    return () => clearTimeout(timer);
  }, [isIOS]);

  const handleInstall = async () => {
    if (busy) return;
    setBusy(true); setError(false);
    const result = await triggerInstall();
    setBusy(false); setShow(false);
    if (result?.outcome === 'accepted' || result?.outcome === 'dismissed') {
      localStore.setItem(DISMISS_KEY, String(Date.now()));
    } else { setError(result?.outcome === 'error'); setShowIOS(true); }
  };
  const dismiss = () => {
    setShow(false); setShowIOS(false);
    localStore.setItem(DISMISS_KEY, String(Date.now()));
  };

  if (!show && !showIOS) return null;

  return (
    <>
      {show && (
        <div className="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 z-[1080] w-[calc(100%-2rem)] max-w-md animate-slide-up">
          <div className="bg-gradient-cta rounded-2xl shadow-xl shadow-flame-600/30 p-4 flex items-center gap-3 text-white">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
              <Flame className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-heading font-bold text-sm">{msg('FE_INSTALL_TITLE', 'Install Holy Grills')}</div>
              <div className="text-xs text-white/80 truncate">{msg('FE_INSTALL_SUBTITLE', 'Add to your home screen for the full experience')}</div>
            </div>
            <button onClick={handleInstall} disabled={busy} className="shrink-0 px-3 py-2 rounded-full bg-card text-primary text-xs font-bold flex items-center gap-1.5 hover:bg-white/90 transition-colors">
              <Download className="w-3.5 h-3.5" /> {msg('FE_INSTALL_ACTION', 'Install')}
            </button>
            <button onClick={dismiss} className="shrink-0 p-1.5 rounded-full hover:bg-white/20 transition-colors" aria-label={msg('FE_PUSH_SOFT_DISMISS', 'Dismiss')}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {showIOS && (
        <ModalPortal>
        <div className="fixed inset-0 z-[1080] flex items-end sm:items-center justify-center hg-scrim animate-fade-in" onClick={dismiss}>
          <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-md mx-auto animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-cta flex items-center justify-center shadow-lg shadow-flame-600/30">
                <Flame className="w-6 h-6 text-white" />
              </div>
              <div>
                <div className="font-heading font-extrabold text-lg text-foreground">{msg('FE_INSTALL_TITLE', 'Install Holy Grills')}</div>
                <div className="text-xs text-muted-foreground">{msg('FE_INSTALL_HOME_SCREEN', 'Add to your Home Screen')}</div>
              </div>
              <button onClick={dismiss} className="ml-auto p-2 rounded-full hover:bg-secondary" aria-label={msg('FE_INSTALL_CLOSE', 'Close')}>
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>
            {error && <p role="alert" className="text-sm text-destructive mb-3">{msg('FE_INSTALL_RETRY_HELP', 'The install prompt could not open. Use your browser menu or try again later.')}</p>}
            {isIOS ? <ol className="space-y-3 text-sm text-foreground">
              <li><Share2 className="inline w-4 h-4 mr-2" />{msg('FE_INSTALL_IOS_SHARE', 'In Safari, tap Share.')}</li>
              <li><Plus className="inline w-4 h-4 mr-2" />{msg('FE_INSTALL_IOS_ADD', 'Choose Add to Home Screen, then tap Add.')}</li>
              <li>{msg('FE_INSTALL_OPEN_APP', 'Open Holy Grills from your home screen to continue.')}</li>
            </ol> : <p className="text-sm text-foreground">{msg('FE_INSTALL_BROWSER_HELP', 'Open this site in Chrome or Edge, open the browser menu and choose Install app or Add to Home Screen. If it is already installed, open Holy Grills from your home screen.')}</p>}
            <button onClick={dismiss} className="mt-5 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">
              {msg('FE_INSTALL_GOT_IT', 'Got it')}
            </button>
          </div>
        </div>
        </ModalPortal>
      )}
    </>
  );
}