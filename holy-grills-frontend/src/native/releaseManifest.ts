import { isNativeApp } from './platform';
import { apiFetch } from './apiFetch';
import APP_CONFIG from '@/config/app.config';
export type AndroidRelease = { available: true; version: string; versionCode: number; url: string; sha256: string };
export function validateAndroidRelease(value: unknown): AndroidRelease | null {
  if (!value || typeof value !== 'object') return null;
  const release = value as Record<string, unknown>;
  if (release.available !== true || typeof release.version !== 'string' || !/^\d+\.\d+\.\d+(?:\+\d+(?:\.\d+)?)?$/.test(release.version) || !Number.isInteger(release.versionCode) || Number(release.versionCode) < 1
      || typeof release.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(release.sha256) || typeof release.url !== 'string') return null;
  let url: URL;
  try { url = new URL(release.url); } catch { return null; }
  if (url.protocol !== 'https:' || url.username || url.password || !url.pathname.endsWith('.apk')) return null;
  const trusted = url.hostname === 'holygrills.online' || (url.hostname === 'github.com' && url.pathname.startsWith('/canibless01/Holy-Grills-/releases/download/'))
    || (url.hostname === 'raw.githubusercontent.com' && /^\/canibless01\/Holy-Grills-\/[a-f0-9]{40}\//i.test(url.pathname));
  return trusted ? release as AndroidRelease : null;
}
let pending: Promise<AndroidRelease | null> | null = null;
let loadedAt = -Infinity;
export function loadAndroidRelease() {
  if (!pending || Date.now() - loadedAt >= 300000 || Date.now() < loadedAt) {
    loadedAt = Date.now();
    pending = apiFetch(new URL('/android-release.json', isNativeApp() ? (APP_CONFIG.domain || 'https://holygrills.online') : window.location.origin).href)
    .then(response => response.ok ? response.json() : null).then(validateAndroidRelease).catch(() => null);
  }
  return pending;
}
