import React from 'react';
import useHydrated from '@/hooks/useHydrated';

/**
 * ClientOnly — renders its children only after hydration has completed.
 *
 * Used for chrome that has no business being in server-rendered HTML and would
 * differ between the server pass and the client's first pass:
 *   - <Toaster /> (portal into document.body)
 *   - <InstallPrompt /> / <CookieConsent /> (read localStorage + window events)
 *
 * On the server and during React's first client render it renders null, so the
 * markup matches; after mount the children appear exactly as they do today.
 */
export default function ClientOnly({ children }: { children?: React.ReactNode }) {
  const hydrated = useHydrated();
  return hydrated ? <>{children}</> : null;
}
