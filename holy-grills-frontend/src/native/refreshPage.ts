import { isNativeApp } from './platform';
import { flushNativeSession } from './secureSession';

/** Explicit user reload: keep the native session durable before restarting the page. */
export async function refreshPage() {
  if (isNativeApp()) await flushNativeSession();
  window.location.reload();
}
