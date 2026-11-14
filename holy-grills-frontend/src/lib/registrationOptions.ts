import { apiClient, getPublicCampusScope } from './apiClient';
import { sessionStore } from './storage';

// Public reference data only; no account, form, password or referral is cached.
const TTL = 60000;
const pending = new Map<string, Promise<any>>();
const valid = (data: any, campus?: string) => data && Array.isArray(data.campuses)
  && Array.isArray(data.departments) && Array.isArray(data.levels)
  && (!campus || data.campus_id === campus);

export async function registrationOptions(params: { campus_id?: string } = {}, force = false) {
  const campus = params.campus_id || getPublicCampusScope() || '';
  const query = campus ? { campus_id: campus } : {};
  const key = `hg_registration_options_v1:${campus || 'default'}`;
  if (!force) {
    try {
      const saved = JSON.parse(sessionStore.getItem(key) || 'null');
      if (saved?.expires > Date.now() && valid(saved.data, campus)) return saved.data;
    } catch { /* a blocked or malformed cache must never block registration */ }
  }
  const existing = pending.get(key);
  if (existing) return structuredClone(await existing);
  const load = async () => {
    for (let attempt = 0; ; attempt++) {
      try {
        const data = await apiClient.get('/auth/registration-options', query, undefined, { timeoutMs: 20000 });
        if (!valid(data, campus)) throw new Error('Registration options unavailable');
        sessionStore.setItem(key, JSON.stringify({ data, expires: Date.now() + TTL }));
        if (data.campus_id) sessionStore.setItem(`hg_registration_options_v1:${data.campus_id}`, JSON.stringify({ data, expires: Date.now() + TTL }));
        return data;
      } catch (error) {
        // Retry only this idempotent read, never account creation. Invalid or
        // retired campus errors retain their campus-picker recovery response.
        if (attempt || !(error.status === 0 || error.status === 429 || error.status >= 500 || error instanceof TypeError)) throw error;
        await new Promise(resolve => setTimeout(resolve, 400));
      }
    }
  };
  const request = load().finally(() => pending.delete(key));
  pending.set(key, request);
  return structuredClone(await request);
}
