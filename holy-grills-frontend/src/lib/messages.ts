import { useEffect, useSyncExternalStore } from 'react';
import { apiClient } from '@/lib/apiClient';

/**
 * Frontend message catalog — copy centralisation.
 * ============================================================================
 * Every user-facing string the backend sends already lives in `app/messages.py`
 * (the `MSG` registry) and is served to the client by `GET /api/messages`. This
 * module is the client half: components and handlers read their own copy through
 * `msg(key, fallback)`, so a wording revamp is a one-file change on the backend.
 *
 * Design rules:
 *   • `fallback` is the string that ships in the bundle. It renders whenever the
 *     catalog has not arrived yet, the key is missing, or the request failed —
 *     the UI never shows a raw key, and never blocks on the fetch.
 *   • `useMessages()` subscribes a component so copy swaps in when the catalog
 *     lands. Handlers that only fire on user action can call `msg()` directly.
 *   • `{token}` placeholders are filled from the `vars` argument.
 *   • `npm run messages:check` fails the build if a `msg('FE_*', …)` call uses a key
 *     the registry does not define (text drift is reported, not fatal).
 */

type Catalog = Record<string, string>;

const EMPTY: Catalog = {};
let catalog: Catalog = EMPTY;
let pending: Promise<void> | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((listener) => listener());
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const getSnapshot = () => catalog;

/** Fetch the catalog once per page load. Safe to call from anywhere. */
export function loadMessages(): Promise<void> {
  if (catalog !== EMPTY) return Promise.resolve();
  if (!pending) {
    pending = apiClient
      // Only the FE_* half — the registry's other keys are API/notification
      // text the client receives in response bodies, so asking for them would
      // triple the payload for nothing.
      .get('/messages', { prefix: 'FE_' })
      .then((res) => {
        const messages = res?.messages;
        if (messages && typeof messages === 'object') {
          catalog = messages as Catalog;
          emit();
        }
      })
      .catch(() => {
        // Registry unreachable (offline, older backend, cold start): every t()
        // keeps its fallback. Never surface this to the user.
      })
      .finally(() => { pending = null; });
  }
  return pending;
}

/**
 * Backend copy for `key`, or the bundled `fallback` when it is unavailable.
 * `{token}` placeholders are replaced from `vars` in both cases.
 */
export function msg(key: string, fallback: string, vars?: Record<string, string | number>): string {
  let text = catalog[key] ?? fallback;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
  }
  return text;
}

/** Re-render this component when the catalog arrives. */
export function useMessages(): void {
  useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => { void loadMessages(); }, []);
}

/** The raw catalog — for diagnostics only; prefer `msg()`. */
export const catalogSnapshot = () => catalog;
