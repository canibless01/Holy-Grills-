import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { subscribeToWebPush, isWebPushSupported } from '@/lib/webPush';
import { isStandalone, hasInstallPrompt, triggerInstall, subscribeInstallPrompt } from '@/lib/installPromptStore';
import StreakPwaBonus from '@/components/streak/StreakPwaBonus';

/** Each step records a real browser action; the server owns eligibility/HP. */
export default function InstallPushBonuses() {
  const { refreshHp } = useHolyGrill();
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [installed, setInstalled] = useState(isStandalone);
  const [installAvailable, setInstallAvailable] = useState(hasInstallPrompt);
  const reload = async () => {
    const updated = await apiClient.get('/challenges/pwa-push-bonus-status');
    setStatus(updated);
    return updated;
  };

  useEffect(() => {
    let active = true;
    apiClient.get('/challenges/pwa-push-bonus-status')
      .then((value) => { if (active) setStatus(value); })
      .catch((failure) => { if (active) setError(failure.message); });
    const onInstalled = () => { setInstalled(true); setInstallAvailable(false); };
    const unsubscribe = subscribeInstallPrompt(() => setInstallAvailable(hasInstallPrompt()));
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      active = false;
      window.removeEventListener('appinstalled', onInstalled);
      unsubscribe();
    };
  }, []);

  const action = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      if (!status) { await reload(); return; }
      if (!status.pwa_install) {
        if (!installed && !isStandalone()) {
          if (!hasInstallPrompt()) throw new Error('Open your browser menu and choose Install app or Add to Home Screen, then open the installed app to continue.');
          const choice = await triggerInstall();
          setInstallAvailable(hasInstallPrompt());
          if (choice?.outcome !== 'accepted') return;
          // Acceptance alone is not proof: appinstalled or standalone confirms it.
          if (!isStandalone() && !installed) return;
        }
        await apiClient.post('/challenges/pwa-installed');
      } else if (!status.push_subscribe) {
        if (!isWebPushSupported()) throw new Error('Push alerts are unavailable in this browser. Open the installed app in a supported browser.');
        if (!await subscribeToWebPush()) throw new Error('Push permission was not granted. You can retry or update site permissions.');
        await apiClient.post('/challenges/push-registered');
      } else if (!status.bonus_completed) {
        await apiClient.post('/challenges/pwa-push-bonus');
      }
      await reload();
      await refreshHp();
    } catch (failure) { setError(failure.message || 'Please try again.'); }
    finally { setBusy(false); }
  };

  return <StreakPwaBonus pwaStatus={status} onAction={action} busy={busy} error={error}
    installed={installed} installAvailable={installAvailable} pushSupported={isWebPushSupported()} />;
}
