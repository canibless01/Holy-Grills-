import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { msg } from '@/lib/messages';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, X, Loader2 } from 'lucide-react';
import { subscribeToWebPush } from '@/lib/webPush';
import { toast } from '@/components/ui/use-toast';

/**
 * Soft prompt to enable push notifications after first order.
 * Shows a non-intrusive banner that can be dismissed.
 * Only shows once per user (tracked via localStorage).
 */
export default function PushSoftPrompt() {
  const { pathname } = useLocation();
  const { user } = useHolyGrill();
  const previousPath = useRef(pathname);
  const seenKey = user?.id ? `hg_push_soft_prompt_seen:${user.id}` : null;
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const arrivedAfterCheckout = previousPath.current !== pathname && pathname.startsWith('/order-confirmation/');
    previousPath.current = pathname;
    // Browsing or reloading a page never triggers a permission/soft prompt.
    // The optional suggestion follows an in-app checkout transition only.
    if (!arrivedAfterCheckout || !seenKey || typeof Notification === 'undefined' || Notification.permission !== 'default') return;
    if (localStorage.getItem(seenKey)) return;
    const timer = setTimeout(() => setShow(true), 3000);
    return () => clearTimeout(timer);
  }, [pathname, seenKey]);

  const handleEnable = async () => {
    setBusy(true);
    try {
      const ok = await subscribeToWebPush();
      if (ok) {
        toast({
          title: msg('FE_INSTALL_PUSH_BONUSES_PUSH_ENABLED', '🔔 Push enabled!'),
          description: msg('FE_INSTALL_PUSH_BONUSES_YOU_LL_RECEIVE_ALERTS_ON_THIS_DEVICE', "You'll receive alerts on this device."),
        });

      }
    } catch (error) {
      toast({
        title: msg('FE_INSTALL_PUSH_BONUSES_COULD_NOT_ENABLE_PUSH', 'Could not enable push'),
        description: msg('FE_PUSH_SOFT_RETRY_SETTINGS', 'You can enable it later in notification settings.'),
        variant: 'destructive',
      });

    }
    finally {
      if (seenKey) localStorage.setItem(seenKey, 'true');
      setShow(false); setBusy(false);
    }
  };

  const handleDismiss = () => {
    if (seenKey) localStorage.setItem(seenKey, 'true');
    setDismissed(true);
    setTimeout(() => setShow(false), 300);
  };

  if (typeof Notification === 'undefined' || Notification.permission === 'granted') {
    return null;
  }

  return (
    <AnimatePresence>
      {show && !dismissed && (
        <motion.div
          initial={{ opacity: 0, y: 50, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-96 z-50"
        >
          <div className="bg-card border border-border rounded-2xl shadow-lg p-4 relative">
            <button
              onClick={handleDismiss}
              className="absolute top-3 right-3 p-1 rounded-full hover:bg-muted transition"
              aria-label={msg('FE_PUSH_SOFT_DISMISS', 'Dismiss')}
            >
              <X className="w-4 h-4 text-muted-foreground" />
            </button>

            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Bell className="w-5 h-5 text-primary" />
              </div>

              <div className="flex-1 pr-6">
                <h3 className="font-bold text-sm text-foreground mb-1">
                  {msg('FE_PUSH_SOFT_TITLE', 'Never miss an update')}
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                  {msg('FE_PUSH_SOFT_BODY', 'Get instant alerts when your order is on the way, when you earn HP, and when rewards are available.')}
                </p>

                <div className="flex gap-2">
                  <button
                    onClick={handleEnable}
                    disabled={busy}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition disabled:opacity-50"
                  >
                    {busy ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Bell className="w-3.5 h-3.5" />
                    )}
                    {msg('FE_PUSH_SOFT_ENABLE', 'Enable notifications')}
                  </button>
                  <button
                    onClick={handleDismiss}
                    className="px-3.5 py-2 rounded-full text-xs font-bold text-muted-foreground hover:text-foreground transition"
                  >
                    {msg('FE_PUSH_SOFT_LATER', 'Maybe later')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
