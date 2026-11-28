import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/apiClient';

export function useCheckoutStore(campus: string | undefined, type: string | null, pin: { lat: number; lng: number } | null, enabled: boolean) {
  const key = JSON.stringify([campus, type, pin?.lat, pin?.lng, enabled]);
  const [result, setResult] = useState<any>(null);
  const [choice, setChoice] = useState<{ key: string; id: string } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    if (!enabled || !campus || !type) { setResult(null); return; }
    setResult({ key, loading: true });
    apiClient.get('/delivery/stores', { delivery_type: type, ...(type === 'off_campus' && pin ? { lat: pin.lat, lon: pin.lng } : {}) }).then(value => {
      if (active) setResult({ key, ...value });
    }).catch(error => { if (active) setResult({ key, error: error.message }); });
    return () => { active = false; };
  }, [key, revision]);
  const current = result?.key === key ? result : null;
  const stores = current?.stores || [];
  const selectedId = choice?.key === key ? choice.id : current?.suggested_store_id || '';
  const selected = stores.find(store => store.id === selectedId) || null;
  return { stores, selected, selectedId, loading: enabled && !!type && (!current || current.loading), error: current?.error,
    choose: (id: string) => setChoice({ key, id }), retry: () => setRevision(value => value + 1) };
}
