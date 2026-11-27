import NativeUpdateNotice from './NativeUpdateNotice';
import NativePullToRefresh from './NativePullToRefresh';
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isNativeApp } from './platform';
import { listenNativeRoutes } from './navigation';

export default function NativeNavigation() {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    if (!isNativeApp()) return;
    return listenNativeRoutes((path, paymentReturn) => navigate(path, { replace: true, state: paymentReturn ? { nativePaymentReturn: Date.now() } : null }));
  }, [navigate]);
  useEffect(() => {
    if (!isNativeApp()) return;
    let removed = false;
    let listener: { remove: () => Promise<void> } | undefined;
    import('@capacitor/app').then(async ({ App }) => {
      listener = await App.addListener('backButton', ({ canGoBack }) => {
        const back = () => {
          if (canGoBack && location.pathname !== '/') navigate(-1);
          else void App.minimizeApp();
        };
        const dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
        if (dialog) {
          const close = dialog.querySelector<HTMLButtonElement>('button[aria-label="Close"], button[aria-label="Dismiss"]');
          if (close) { close.click(); return; }
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          // A required campus picker may intentionally reject Escape. Android
          // Back must still be able to leave/minimize instead of trapping users.
          setTimeout(() => { if (dialog.isConnected) back(); }, 50);
          return;
        }
        back();
      });
      if (removed) await listener.remove();
    });
    return () => { removed = true; void listener?.remove(); };
  }, [navigate, location.pathname]);
  return isNativeApp() ? <><NativePullToRefresh /><NativeUpdateNotice /></> : null;
}
