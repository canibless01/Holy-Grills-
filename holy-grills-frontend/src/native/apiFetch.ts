import { CapacitorHttp } from '@capacitor/core';
import { isNativeApp } from './platform';

/** Native HTTPS transport for the existing bearer-token API; web fetch is unchanged. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  if (!isNativeApp()) return fetch(input, init);
  const url = new URL(input);
  if (url.protocol !== 'https:') throw new Error('Android API requests require HTTPS');
  if (init.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const headers = Object.fromEntries(new Headers(init.headers).entries());
  let data = init.body;
  if (typeof data === 'string' && new Headers(init.headers).get('Content-Type')?.includes('application/json')) data = JSON.parse(data);
  const request = CapacitorHttp.request({ url: input, method: init.method || 'GET', headers,
    data, responseType: 'text', connectTimeout: 15000, readTimeout: 30000 });
  const native = await new Promise<Awaited<typeof request>>((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'));
    init.signal?.addEventListener('abort', abort, { once: true });
    request.then(resolve, reject).finally(() => init.signal?.removeEventListener('abort', abort));
  });
  const body = native.status === 204 || native.status === 304 ? null : typeof native.data === 'string' ? native.data : JSON.stringify(native.data);
  return new Response(body, { status: native.status, headers: native.headers });
}
