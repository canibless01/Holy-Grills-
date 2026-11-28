import { useRef } from 'react';
import { useCampus } from './campusContext';

/** A failed response reuses the UUID; changed input or a successful save starts a new request. */
export function useCmsCreateIntent() {
  const { campusId, adminCampusId } = useCampus();
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  return {
    body: <T extends Record<string, unknown>>(input: T): T & { request_id: string } => {
      const fingerprint = JSON.stringify([campusId, adminCampusId, input]);
      if (pending.current?.fingerprint !== fingerprint) {
        pending.current = { fingerprint, id: crypto.randomUUID() };
      }
      return { ...input, request_id: pending.current.id };
    },
    clear: () => { pending.current = null; },
  };
}
