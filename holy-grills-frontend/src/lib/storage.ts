/**
 * SSR-safe storage
 * ============================================================================
 * The app keeps JWTs and small preferences in localStorage/sessionStorage. On a
 * server render (Track B pre-rendering) neither object exists, and a bare
 * `localStorage.getItem(...)` at module scope or during render would throw
 * `ReferenceError: localStorage is not defined`.
 *
 * These shims behave exactly like the browser APIs when a DOM is present, and
 * fall back to a per-process in-memory map when it is not. The fallback starts
 * EMPTY, which is what keeps user data out of server-rendered HTML: a server
 * render can only ever see the guest state.
 *
 * Browser behaviour is unchanged: the same keys, the same string values, the
 * same storage objects.
 */

const memory = new Map<string, string>();

const hasLocal = () => typeof window !== 'undefined' && !!window.localStorage;
const hasSession = () => typeof window !== 'undefined' && !!window.sessionStorage;

const make = (has: () => boolean, kind: 'local' | 'session') => ({
  getItem(key: string): string | null {
    try {
      if (has()) return window[kind === 'local' ? 'localStorage' : 'sessionStorage'].getItem(key);
    } catch { /* private mode / disabled storage — fall through to memory */ }
    return memory.get(key) ?? null;
  },
  setItem(key: string, value: string): void {
    try {
      if (has()) {
        window[kind === 'local' ? 'localStorage' : 'sessionStorage'].setItem(key, value);
        return;
      }
    } catch { /* fall through to memory */ }
    memory.set(key, value);
  },
  removeItem(key: string): void {
    try {
      if (has()) window[kind === 'local' ? 'localStorage' : 'sessionStorage'].removeItem(key);
    } catch { /* ignore */ }
    memory.delete(key);
  },
});

/** Drop-in replacement for `localStorage` that is safe during a server render. */
export const localStore = make(hasLocal, 'local');
/** Drop-in replacement for `sessionStorage` that is safe during a server render. */
export const sessionStore = make(hasSession, 'session');
