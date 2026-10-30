// Imported eagerly by the root install UI: capture the browser event even when
// the rewards/streak routes have not been visited. All entry points share it.
let deferredPrompt: any = null;
let consumed = false;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach(listener => listener());
export const subscribeInstallPrompt = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

export const isStandalone = () => typeof window !== 'undefined' &&
  (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true);
export const hasInstallPrompt = () => !consumed && !!deferredPrompt;
export const openInstallHelp = () => window.dispatchEvent(new Event('hg:install-help'));

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    consumed = false;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    consumed = true;
    notify();
  });
}

export const triggerInstall = async () => {
  if (!deferredPrompt || consumed) return { outcome: 'unavailable' };
  const prompt = deferredPrompt;
  // Claim before awaiting so simultaneous UI entry points cannot prompt twice.
  consumed = true;
  deferredPrompt = null;
  notify();
  try {
    await prompt.prompt();
    return await prompt.userChoice;
  } catch {
    return { outcome: 'error' };
  }
};
