import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';

type PickupPoint = { enabled: true; name: string; address: string; instructions: string; fee: number };

export function useStorePickup(campus: string | undefined, enabled: boolean) {
  const [result, setResult] = useState<{ campus: string; option?: PickupPoint; failed?: boolean } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    if (campus && enabled) {
      apiClient.get('/delivery/store-pickup').then(value => {
        if (active) setResult({ campus, option: value.enabled === true ? value : undefined });
      }).catch(() => { if (active) setResult({ campus, failed: true }); });
    }
    return () => { active = false; };
  }, [campus, enabled, revision]);
  const current = enabled && result?.campus === campus ? result : null;
  return { option: current?.option || null, error: !!current?.failed, retry: () => setRevision(v => v + 1) };
}
