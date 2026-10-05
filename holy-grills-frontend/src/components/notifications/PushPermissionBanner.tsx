import { useState } from 'react';
import { motion } from 'framer-motion';
import { Bell, BellRing, BellOff, Loader2 } from 'lucide-react';
import { subscribeToWebPush } from '@/lib/webPush';

// Browser push-permission status banner. The preference toggles (push_enabled)
// are the backend-backed part of this screen; this banner reflects the
// browser's Notification permission only. Push subscription is handled by the
// native Web Push API — on grant it POSTs /push/subscribe (see webPush.js),
// which stores the browser PushSubscription for server-side delivery.
export default function PushPermissionBanner() {
  const [permission, setPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default'
  );
  const [busy, setBusy] = useState(false);

  const enable = async () => {
    setBusy(true);
    try {
      // Native Web Push — requests Notification permission, subscribes via
      // PushManager, and POSTs the subscription to /push/subscribe.
      const ok = await subscribeToWebPush();
      setPermission(ok ? 'granted' : (typeof Notification !== 'undefined' ? Notification.permission : 'default'));
    } catch { /* permission denied or browser unsupported — banner reflects status */ }
    setBusy(false);
  };

  if (permission === 'granted') {
    return (
      <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-success/10 border border-success/25">
        <div className="w-10 h-10 rounded-xl bg-success/15 flex items-center justify-center flex-shrink-0">
          <BellRing className="w-5 h-5 text-success" />
        </div>
        <div className="flex-1">
          <div className="font-bold text-sm text-foreground">Push notifications enabled</div>
          <div className="text-[11px] text-muted-foreground">You'll receive alerts on this device.</div>
        </div>
      </div>
    );
  }

  const denied = permission === 'denied';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex items-center gap-3 p-3.5 rounded-2xl border ${
        denied ? 'bg-destructive/5 border-destructive/20' : 'bg-accent/10 border-accent/30'
      }`}
    >
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
        denied ? 'bg-destructive/10' : 'bg-accent/20'
      }`}>
        {denied ? <BellOff className="w-5 h-5 text-destructive" /> : <Bell className="w-5 h-5 text-accent-foreground" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm text-foreground">
          {denied ? 'Push is blocked' : 'Enable push notifications'}
        </div>
        <div className="text-[11px] text-muted-foreground leading-snug">
          {denied
            ? 'Update your browser site settings to allow notifications.'
            : 'Get instant alerts for orders, HP and delivery.'}
        </div>
      </div>
      {!denied && (
        <button
          onClick={enable}
          disabled={busy}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bell className="w-3.5 h-3.5" />}
          Enable
        </button>
      )}
    </motion.div>
  );
}