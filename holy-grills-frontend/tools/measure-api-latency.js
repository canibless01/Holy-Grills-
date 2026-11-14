/**
 * Holy Grills — API latency + skeleton policy harness
 * ====================================================
 * The skeleton rule (section 7 of the verification brief) keys off measured
 * Flask latency per screen, and that can only be measured from a browser that
 * can reach the backend. Paste this whole file into the DevTools console on the
 * running app, signed in as the role you want to measure, then navigate the
 * screens you care about.
 *
 * It patches window.fetch and reports a live table:
 *   endpoint | method | count | p50 | p95 | max | non-2xx | verdict
 *
 * Verdict follows the policy in docs/PERF_SKELETONS.md:
 *   <100 ms  -> SKELETON OPTIONAL (render directly)
 *   100-300  -> KEEP SKELETON
 *   >300 ms  -> KEEP SKELETON + FIX ENDPOINT
 *
 * Print the summary at any time with:  __hgLatency.report()
 * Reset between screens with:          __hgLatency.reset()
 */
(() => {
  const rows = new Map();

  const key = (method, url) => {
    let u = url;
    try {
      u = new URL(url, location.origin).pathname;
    } catch { /* relative string, keep as-is */ }
    return `${method} ${u}`;
  };

  const now = () => performance.now();

  const record = (method, url, ms, status) => {
    const k = key(method, url);
    const row = rows.get(k) || { method, url: k.split(' ').slice(1).join(' '), times: [], errors: 0 };
    row.times.push(ms);
    if (status >= 400 || status === 0) row.errors += 1;
    rows.set(k, row);
  };

  const original = window.fetch;
  window.fetch = async function (input, init = {}) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = (init.method || (input && input.method) || 'GET').toUpperCase();
    const t0 = now();
    try {
      const res = await original.apply(this, arguments);
      record(method, url, now() - t0, res.status);
      return res;
    } catch (err) {
      record(method, url, now() - t0, 0);
      throw err;
    }
  };

  const pct = (sorted, p) => sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];

  const verdict = (p50) =>
    p50 < 100 ? 'skeleton optional' : p50 <= 300 ? 'keep skeleton' : 'keep skeleton + fix endpoint';

  const report = () => {
    const out = [...rows.values()]
      .filter((r) => r.url.startsWith('/api'))
      .map((r) => {
        const sorted = [...r.times].sort((a, b) => a - b);
        const p50 = Math.round(pct(sorted, 50));
        return {
          endpoint: r.method + ' ' + r.url,
          calls: r.times.length,
          p50,
          p95: Math.round(pct(sorted, 95)),
          max: Math.round(sorted[sorted.length - 1]),
          errors: r.errors,
          verdict: verdict(p50),
        };
      })
      .sort((a, b) => b.p50 - a.p50);
    // eslint-disable-next-line no-console
    console.table(out);
    return out;
  };

  window.__hgLatency = {
    report,
    reset: () => rows.clear(),
    raw: rows,
  };

  // eslint-disable-next-line no-console
  console.info('[hg] API latency recorder active — navigate the app, then run __hgLatency.report()');
})();
