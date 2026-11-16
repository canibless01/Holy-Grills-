import { useEffect, useState } from 'react';

/**
 * useHydrated — false during a server render AND during React's first
 * client-side pass, true afterwards.
 *
 * Why it exists: pre-rendered HTML must match the markup React produces on its
 * first hydration render, or React discards the server DOM and logs a
 * hydration mismatch. Anything that depends on browser-only state (a token in
 * localStorage, a media query, `window` size) therefore has to render its
 * server-safe branch first and switch after mount.
 *
 * Typical use:
 *   const hydrated = useHydrated();
 *   {hydrated && user ? <UserMenu /> : <SignInLink />}
 */
export default function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => { setHydrated(true); }, []);
  return hydrated;
}
