import { CapacitorHttp } from '@capacitor/core';
import { isNativeApp } from './platform';

/** Web transport is unchanged. Only native reads may retry a transient failure;
 * charges, orders, reward claims and other mutations are never replayed here. */
export async function apiFetch(input: string, init: RequestInit = {}, timeoutMs = 30000): Promise<Response> {
  if (!isNativeApp()) return fetch(input, init);
  const url = new URL(input);
  if (url.protocol !== 'https:') throw new Error('Android API requests require HTTPS');
  const aborted = () => { if (init.signal?.aborted) throw new DOMException('Aborted', 'AbortError'); };
  aborted();
  const headers = Object.fromEntries(new Headers(init.headers).entries());
  let data = init.body;
  if (typeof data === 'string' && new Headers(init.headers).get('Content-Type')?.includes('application/json')) data = JSON.parse(data);
  const method = init.method || 'GET';
  const read = ['GET', 'HEAD'].includes(method.toUpperCase());
  const once = () => {
    aborted();
    const request = CapacitorHttp.request({ url: input, method, headers, data, responseType: 'text',
      connectTimeout: Math.min(timeoutMs, 15000), readTimeout: timeoutMs });
    return new Promise<Awaited<typeof request>>((resolve, reject) => {
      const abort = () => reject(new DOMException('Aborted', 'AbortError'));
      init.signal?.addEventListener('abort', abort, { once: true });
      request.then(resolve, reject).finally(() => init.signal?.removeEventListener('abort', abort));
    });
  };
  let native: Awaited<ReturnType<typeof once>>;
  let retried = false;
  try { native = await once(); }
  catch (failure) {
    aborted();
    if (!read || (failure as Error)?.name === 'AbortError') throw failure;
    retried = true;
    native = await once(); // One bounded read retry; the caller's deadline still applies.
  }
  if (read && !retried && [502, 503, 504].includes(native.status)) native = await once();
  aborted();
  const body = native.status === 204 || native.status === 304 ? null : typeof native.data === 'string' ? native.data : JSON.stringify(native.data);
  return new Response(body, { status: native.status, headers: native.headers });
}
