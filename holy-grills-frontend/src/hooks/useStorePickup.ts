import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';

type PickupPoint = { enabled: true; name: string; address: string; instructions: string; fee: number; requires_store_selection?: boolean };

export function useStorePickup(campus: string | undefined, enabled: boolean, storeId?: string) {
  const key = JSON.stringify([campus, storeId]);
  const [result, setResult] = useState<{ campus: string; option?: PickupPoint; failed?: boolean } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    if (campus && enabled) {
      apiClient.get('/delivery/store-pickup', storeId ? { store_id: storeId } : undefined).then(value => {
        if (active) setResult({ campus: key, option: value.enabled === true ? value : undefined });
      }).catch(() => { if (active) setResult({ campus: key, failed: true }); });
    }
    return () => { active = false; };
  }, [campus, storeId, enabled, revision]);
  const current = enabled && result?.campus === key ? result : null;
  return { option: current?.option || null, error: !!current?.failed, retry: () => setRevision(v => v + 1) };
}
