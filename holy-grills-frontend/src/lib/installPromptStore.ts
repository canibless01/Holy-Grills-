// Captures the PWA `beforeinstallprompt` event so any component can trigger
// the native install flow on demand. The listener is registered at module-eval
// time — the Streak page imports this eagerly via App.tsx, so it's ready before
// the event fires. A consumed prompt can only be used once per browser event.
let deferredPrompt = null;
let consumed = false;

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    consumed = false;
  });
}

export const isStandalone = () =>
  typeof window !== 'undefined' &&
  (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true);

export const hasInstallPrompt = () => !consumed && !!deferredPrompt;

// Triggers the native install prompt and returns the user's choice
// ({ outcome: 'accepted' | 'dismissed' }) or 'unavailable'/'error'.
export const triggerInstall = async () => {
  if (!deferredPrompt || consumed) return { outcome: 'unavailable' };
  try {
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    consumed = true;
    return choice;
  } catch {
    consumed = true;
    return { outcome: 'error' };
  }
};