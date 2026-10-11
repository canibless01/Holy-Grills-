// Off-campus delivery helpers — distance calculation + nearest-gate detection.
// Gates come from the backend (GET /delivery/gates) with lat/lng coordinates.

// Haversine distance in kilometres between two lat/lng points.
export function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Find the gate nearest to a pin location.
export function findNearestGate(gates, lat, lng) {
  if (!gates || !gates.length || lat == null || lng == null) return null;
  let best = null;
  let bestKm = Infinity;
  for (const g of gates) {
    const gLat = g.lat ?? g.latitude;
    const gLng = g.lng ?? g.lon ?? g.longitude;
    if (gLat == null || gLng == null) continue;
    const km = haversineKm(lat, lng, gLat, gLng);
    if (km < bestKm) { bestKm = km; best = { gate: g, km }; }
  }
  return best ? { gate: best.gate, km: bestKm } : null;
}

// Estimated delivery time label from a distance.
export function etaLabel(km) {
  if (km == null || isNaN(km)) return '15-20 min';
  if (km <= 1) return '10-15 min';
  if (km <= 3) return '15-20 min';
  if (km <= 5) return '20-30 min';
  return '30-45 min';
}

// One decimal place kilometre label.
export function formatKm(km) {
  if (km == null || isNaN(km)) return '—';
  return `${km.toFixed(1)}km`;
}
// ── Off-campus fee cache ────────────────────────────────────────────────────
// Dropping a pin calls calculate-fee, which makes several database calls in a
// row (campus, radius setting, gates, zones). On a cold or idle backend the
// FIRST call is the slow one, so a guest dragging the pin around re-pays that
// cost on every move. Keyed on the pin rounded to ~11 m: a re-drop on the same
// spot answers instantly, and a genuinely new position still asks the backend.
const FEE_CACHE = new Map();
const FEE_CACHE_MAX = 40;

export const feeCacheKey = (lat, lng) => `${lat.toFixed(4)},${lng.toFixed(4)}`;

export const readFeeCache = (lat, lng) => FEE_CACHE.get(feeCacheKey(lat, lng)) || null;

export const writeFeeCache = (lat, lng, value) => {
  // Simple bound — the checkout screen is short-lived, so evicting the oldest
  // entry is enough and no timestamp bookkeeping is needed.
  if (FEE_CACHE.size >= FEE_CACHE_MAX) {
    const oldest = FEE_CACHE.keys().next().value;
    if (oldest !== undefined) FEE_CACHE.delete(oldest);
  }
  FEE_CACHE.set(feeCacheKey(lat, lng), value);
};
