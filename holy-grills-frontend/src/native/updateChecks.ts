import type { AndroidRelease } from './releaseManifest';

/** Coalesced resume checks, daily after success; network failures can retry later. */
export function createUpdateCheck(options: {
  getInfo: () => Promise<{ id: string; build: string }>;
  load: () => Promise<AndroidRelease | null>;
  lastSuccess: () => number;
  markSuccess: (time: number) => void;
  onUpdate: (release: AndroidRelease) => void;
  now?: () => number;
}) {
  let active = true, pending = false, lastAttempt = -Infinity;
  const now = options.now || Date.now;
  return {
    stop() { active = false; },
    async check() {
      const time = now(), saved = options.lastSuccess();
      if (!active || pending || (saved > 0 && time >= saved && time - saved < 86400000)
        || (time >= lastAttempt && time - lastAttempt < 300000)) return;
      pending = true; lastAttempt = time;
      try {
        const info = await options.getInfo();
        if (!active || info.id.endsWith('.debug')) return;
        const available = await options.load();
        if (!active || !available) return;
        options.markSuccess(now());
        if (available.versionCode > Number(info.build)) options.onUpdate(available);
      } catch { /* Optional update checks must not interrupt orders or login. */ }
      finally { pending = false; }
    },
  };
}
