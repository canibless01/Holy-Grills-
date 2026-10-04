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