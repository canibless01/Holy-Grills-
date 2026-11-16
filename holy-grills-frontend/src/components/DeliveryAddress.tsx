import { MapPin } from 'lucide-react';

/** Persisted checkout address, available before rider assignment. No geocoder call. */
export default function DeliveryAddress({ order }: { order: any }) {
  const address = order.delivery_address_snapshot || order.delivery_address || {};
  const lines = [...new Set([address.location_name, address.line1, address.landmark].filter((v) => typeof v === 'string' && v.trim()).map((v) => v.trim()))] as string[];
  const rawLat = order.delivery_location_lat ?? address.latitude;
  const rawLon = order.delivery_location_lon ?? address.longitude;
  const lat = Number(rawLat), lon = Number(rawLon);
  const hasPin = rawLat != null && rawLat !== '' && rawLon != null && rawLon !== '' && Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  if (!lines.length && !hasPin) return null;
  return <div className="my-2 flex items-start gap-2 rounded-xl bg-secondary/60 p-2.5 text-xs">
    <MapPin aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
    <div className="min-w-0 space-y-1"><p className="break-words font-medium text-foreground">{lines.join(' · ') || 'Pinned delivery location'}</p>
      {hasPin && <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${lat},${lon}`)}`} target="_blank" rel="noopener noreferrer" className="inline-block font-semibold text-primary underline">View delivery pin on Google Maps</a>}
    </div>
  </div>;
}
