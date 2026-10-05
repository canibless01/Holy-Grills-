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

const DISMISS_KEY = 'hg_install_dismissed';

export default function InstallPrompt() {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);
  const [showIOS, setShowIOS] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY) === '1') return;
    if (window.matchMedia('(display-mode: standalone)').matches) return; // already installed

    const onBIP = (e) => {
      e.preventDefault();
      setDeferred(e);
      setShow(true);
    };
    window.addEventListener('beforeinstallprompt', onBIP);
    return () => window.removeEventListener('beforeinstallprompt', onBIP);
  }, []);

  // iOS Safari has no beforeinstallprompt — detect and offer instructions.
  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY) === '1') return;
    const isIOS = /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase());
    const isSafari = /safari/.test(navigator.userAgent.toLowerCase()) && !/crios|fxios/.test(navigator.userAgent.toLowerCase());
    if (isIOS && isSafari && !window.navigator.standalone) {
      const t = setTimeout(() => setShowIOS(true), 4000);
      return () => clearTimeout(t);
    }
  }, []);

  const handleInstall = async () => {
    if (!deferred) return;
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    setDeferred(null);
    setShow(false);
    if (outcome === 'accepted' || outcome === 'dismissed') {
      localStorage.setItem(DISMISS_KEY, '1');
    }
  };

  const dismiss = () => {
    setShow(false);
    setShowIOS(false);
    localStorage.setItem(DISMISS_KEY, '1');
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
              <div className="font-heading font-bold text-sm">Install Holy Grill</div>
              <div className="text-xs text-white/80 truncate">Add to your home screen for the full experience</div>
            </div>
            <button onClick={handleInstall} className="shrink-0 px-3 py-2 rounded-full bg-white text-primary text-xs font-bold flex items-center gap-1.5 hover:bg-white/90 transition-colors">
              <Download className="w-3.5 h-3.5" /> Install
            </button>
            <button onClick={dismiss} className="shrink-0 p-1.5 rounded-full hover:bg-white/20 transition-colors" aria-label="Dismiss">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {showIOS && (
        <div className="fixed inset-0 z-[1080] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-md animate-fade-in" onClick={dismiss}>
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-md mx-auto animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-cta flex items-center justify-center shadow-lg shadow-flame-600/30">
                <Flame className="w-6 h-6 text-white" />
              </div>
              <div>
                <div className="font-heading font-extrabold text-lg text-foreground">Install Holy Grill</div>
                <div className="text-xs text-muted-foreground">Add to your Home Screen</div>
              </div>
              <button onClick={dismiss} className="ml-auto p-2 rounded-full hover:bg-secondary" aria-label="Close">
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>
            <ol className="space-y-3 text-sm text-foreground">
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">1</span>
                <span>Tap the <strong>Share</strong> button in Safari's toolbar <Share2 className="inline w-3.5 h-3.5 mx-0.5 text-primary" /></span>
              </li>
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">2</span>
                <span>Scroll down and tap <strong>Add to Home Screen</strong> <Plus className="inline w-3.5 h-3.5 mx-0.5 text-primary" /></span>
              </li>
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary/15 text-primary font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">3</span>
                <span>Tap <strong>Add</strong> — Holy Grill will appear on your home screen</span>
              </li>
            </ol>
            <button onClick={dismiss} className="mt-5 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}