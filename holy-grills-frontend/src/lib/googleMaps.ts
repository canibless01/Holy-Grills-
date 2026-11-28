let pending: Promise<any> | null = null;
let authenticationFailed = false;

/** Bound SDK library loading too: script success alone does not prove tiles or Places loaded. */
export function mapsDeadline<T>(operation: Promise<T>, ms = 20000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('maps_timeout')), ms);
    operation.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}
export function loadGoogleMaps(): Promise<any> {
  if (authenticationFailed) return Promise.reject(new Error('maps_authentication'));
  if ((window as any).google?.maps?.version && (window as any).google.maps.importLibrary) return Promise.resolve((window as any).google.maps);
  if (pending) return pending;
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  if (!key) return Promise.reject(new Error('maps_not_configured'));
  pending = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.dataset.hgGoogleMaps = 'true';
    let timer: ReturnType<typeof setTimeout>;
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer); delete (window as any).__hgGoogleMapsReady;
      if (error) { script.remove(); pending = null; reject(error); }
      else resolve((window as any).google.maps);
    };
    (window as any).gm_authFailure = () => {
      authenticationFailed = true;
      finish(new Error('maps_authentication'));
      window.dispatchEvent(new Event('hg:maps-auth-error'));
    };
    (window as any).__hgGoogleMapsReady = () => finish();
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&loading=async&v=quarterly&callback=__hgGoogleMapsReady`;
    script.async = true; script.onerror = () => finish(new Error('maps_unavailable'));
    timer = setTimeout(() => finish(new Error('maps_timeout')), 20000);
    document.head.appendChild(script);
  });
  return pending;
}
