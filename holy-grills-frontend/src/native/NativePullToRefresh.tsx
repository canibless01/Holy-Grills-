import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { installPullRefresh } from './pullRefresh';
import { refreshPage } from './refreshPage';
import { msg } from '@/lib/messages';

export default function NativePullToRefresh() {
  const [distance, setDistance] = useState(0), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false);
  useEffect(() => installPullRefresh(setDistance, async () => {
    setBusy(true); setFailed(false);
    try {
      // Explicit user refresh, like browser pull-to-refresh. Never retry an
      // order/payment POST. Persist the native session before restarting reads.
      await refreshPage();
    } catch { setBusy(false); setFailed(true); }
  }), []);
  if (!distance && !busy && !failed) return null;
  return <div role="status" className="fixed left-1/2 top-3 z-[90] -translate-x-1/2 rounded-full border bg-card px-4 py-2 text-xs font-bold shadow-lg flex items-center gap-2">
    <RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
    {failed ? msg('FE_ANDROID_REFRESH_FAILED', 'Refresh could not start. Please try again.') : busy ? msg('FE_ANDROID_REFRESHING', 'Refreshing…') : distance >= 80 ? msg('FE_ANDROID_RELEASE_REFRESH', 'Release to refresh') : msg('FE_ANDROID_PULL_REFRESH', 'Pull to refresh')}
  </div>;
}
