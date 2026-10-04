// Storefront operating-hours helpers (storefront.py /storefront/operating-hours).
//
// The backend returns { schedule, today_override, is_open } where:
//   - schedule: rows keyed by weekday (0=Mon … 6=Sun) with opens_at/closes_at + is_closed
//   - today_override: a single date override for today (or null)
//   - is_open: boolean when a campus is chosen, null when it isn't
//
// The backend does NOT return the next opening time, so when the kitchen is
// closed we compute it here from the same schedule the backend already
// authored. This is a display helper over backend data — it never decides
// open/closed on its own (is_open is the backend's call).

// WAT is UTC+1 with no DST. Shift the epoch +1h and read the UTC fields so the
// wall-clock math stays correct on a device set to any timezone.
const WAT_OFFSET_MS = 60 * 60 * 1000;
const watNow = () => new Date(Date.now() + WAT_OFFSET_MS);
const toIsoDate = (d) => d.toISOString().slice(0, 10); // YYYY-MM-DD of the WAT wall-clock
const toMinutes = (t) => {
  if (!t) return null;
  const [h, m] = String(t).split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
};
// JS getUTCDay: 0=Sun..6=Sat. The schedule uses 0=Mon..6=Sun.
const scheduleWeekday = (jsDay) => (jsDay === 0 ? 6 : jsDay - 1);

/**
 * Compute the next time the kitchen opens, from the weekly schedule + today's
 * override. Returns { date: 'YYYY-MM-DD', time: 'HH:MM' } in WAT, or null when
 * no open day exists in the next week.
 *
 * Only today's override is known (the endpoint returns just today_override),
 * so future days use the weekly schedule — accurate for the countdown display.
 */
export function computeNextOpening(schedule, todayOverride) {
  const rows = Array.isArray(schedule) ? schedule : [];
  const byWeekday = new Array(7).fill(null);
  rows.forEach((r) => { if (r && r.weekday != null) byWeekday[r.weekday] = r; });

  const now = watNow();
  const nowMin = now.getUTCHours() * 60 + now.getUTCMinutes();

  for (let offset = 0; offset < 8; offset++) {
    const day = new Date(now.getTime() + offset * 86400000);
    const weekday = scheduleWeekday(day.getUTCDay());
    const isoDate = toIsoDate(day);

    // Today's override wins for offset 0.
    if (offset === 0 && todayOverride) {
      if (todayOverride.is_closed) continue;
      const open = toMinutes(todayOverride.opens_at);
      const close = toMinutes(todayOverride.closes_at);
      if (open == null || close == null) continue;
      if (nowMin < close) return nowMin < open ? { date: isoDate, time: todayOverride.opens_at } : null;
      continue;
    }

    const row = byWeekday[weekday];
    if (!row || row.is_closed) continue;
    const open = toMinutes(row.opens_at);
    const close = toMinutes(row.closes_at);
    if (open == null || close == null) continue;
    if (offset === 0) {
      if (nowMin < open) return { date: isoDate, time: row.opens_at };
      if (nowMin < close) return null; // open right now — caller said closed, so skip
      continue;
    }
    return { date: isoDate, time: row.opens_at };
  }
  return null;
}