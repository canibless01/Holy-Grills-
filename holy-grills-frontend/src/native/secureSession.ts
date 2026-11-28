import { registerPlugin } from '@capacitor/core';
import { isNativeApp } from './platform';

interface SecureSessionPlugin {
  load(): Promise<{ access?: string; refresh?: string }>;
  save(value: { access: string | null; refresh: string | null }): Promise<void>;
  clear(): Promise<void>;
}
const vault = registerPlugin<SecureSessionPlugin>('HolyGrillsSecureSession');
const keys = new Set(['hg_access_token', 'hg_refresh_token']);
const cache = new Map<string, string>();
let ready = false;
let scheduled = false;
let writes: Promise<void> = Promise.resolve();
let failure: unknown = null;

export const isNativeCredential = (key: string) => isNativeApp() && keys.has(key);
export const readNativeCredential = (key: string) => cache.get(key) || null;

export async function restoreNativeSession() {
  if (!isNativeApp() || ready) return;
  // Never import browser tokens into the native vault. A fresh install logs in.
  for (const store of [localStorage, sessionStorage]) for (const key of keys) store.removeItem(key);
  const saved = await vault.load(); // Fail closed: bootstrap offers Retry on vault failure.
  if (localStorage.getItem('hg_remember') !== '0') {
    if (saved.access) cache.set('hg_access_token', saved.access);
    if (saved.refresh) cache.set('hg_refresh_token', saved.refresh);
  } else await vault.clear();
  ready = true;
}

function scheduleWrite() {
  if (scheduled) return;
  scheduled = true;
  queueMicrotask(() => {
    scheduled = false;
    const remember = localStorage.getItem('hg_remember') !== '0';
    const value = { access: remember ? cache.get('hg_access_token') || null : null,
      refresh: remember ? cache.get('hg_refresh_token') || null : null };
    // Snapshot and serialize. A late login/refresh write cannot undo logout.
    writes = writes.catch(() => {}).then(async () => {
      if (value.access || value.refresh) await vault.save(value); else await vault.clear();
      failure = null;
    }).catch(error => { failure = error; window.dispatchEvent(new Event('hg:native-session-error')); });
  });
}
export function writeNativeCredential(key: string, value: string | null) {
  if (!ready) throw new Error('Native session has not been restored');
  if (value) cache.set(key, value); else cache.delete(key);
  scheduleWrite();
}
export async function flushNativeSession() {
  await Promise.resolve(); // Let the coalesced setTokens operation snapshot both values.
  await writes;
  if (failure) throw failure;
}

export async function resetNativeSession() {
  await writes;
  await vault.clear(); cache.clear(); failure = null; ready = true;
}
