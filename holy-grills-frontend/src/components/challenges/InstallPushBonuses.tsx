import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { subscribeToWebPush } from '@/lib/webPush';
import StreakPwaBonus from '@/components/streak/StreakPwaBonus';

/**
 * InstallPushBonuses — the app-install + push-subscribe bonuses, living
 * permanently under Challenges. It owns its own backend calls so it can be
 * dropped anywhere without the host page wiring anything up.
 */
export default function InstallPushBonuses() {
  const { refreshHp } = useHolyGrill();
  const [pwaStatus, setPwaStatus] = useState(null);
  const [pushLoading, setPushLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient.get('/challenges/pwa-push-bonus-status')
      .then((s) => { if (!cancelled) setPwaStatus(s); })
      .catch(() => { /* bonus not configured yet — card stays hidden */ });
    return () => { cancelled = true; };
  }, []);

  // Auto-claim the install bonus when running as an installed app and the
  // backend hasn't recorded it yet. POST /api/challenges/pwa-installed is the
  // only trigger point — nothing awards automatically.
  useEffect(() => {
    if (!pwaStatus || pwaStatus.pwa_install) return;
    if (!window.matchMedia('(display-mode: standalone)').matches) return;
    apiClient.post('/challenges/pwa-installed')
      .then(async (res) => {
        if (res?.hp_awarded && !res?.already_completed) {
          await refreshHp();
          toast({ title: '🎉 PWA install bonus!', description: `+${res.hp_awarded} HP added to your wallet.` });
        }
        const updated = await apiClient.get('/challenges/pwa-push-bonus-status').catch(() => null);
        if (updated) setPwaStatus(updated);
      })
      .catch(() => { /* milestone may not be configured — silent */ });
  }, [pwaStatus?.pwa_install]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleEnablePush = async () => {
    setPushLoading(true);
    try {
      // Native Web Push — requests permission, subscribes via PushManager, and
      // registers the subscription with the backend (POST /push/subscribe).
      const ok = await subscribeToWebPush();
      if (!ok) throw new Error('Push permission was not granted.');

      await refreshHp();
      const updated = await apiClient.get('/challenges/pwa-push-bonus-status').catch(() => null);
      if (updated) setPwaStatus(updated);
      toast({ title: '🔔 Push enabled!', description: 'You\'ll receive alerts on this device.' });
    } catch (e) {
      toast({ title: 'Could not enable push', description: e.message, variant: 'destructive' });
    }
    setPushLoading(false);
  };

  return <StreakPwaBonus pwaStatus={pwaStatus} onEnablePush={handleEnablePush} pushLoading={pushLoading} />;
}