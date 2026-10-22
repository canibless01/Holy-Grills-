import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LocateFixed, MapPin, Search, X, Loader2 } from 'lucide-react';
import { formatKm, etaLabel } from '@/lib/deliveryUtils';
import type { DeliveryGate } from '@/types/delivery';

// Centroid of the gates — used as the map's initial view.
const centroid = (gates?: DeliveryGate[]): [number, number] => {
  const valid = (gates || []).filter((g) => (g.lat ?? g.latitude) != null && (g.lng ?? g.lon ?? g.longitude) != null);
  if (!valid.length) return [7.295, 5.14]; // Akure fallback
  const lat = valid.reduce((s, g) => s + Number(g.lat ?? g.latitude), 0) / valid.length;
  const lng = valid.reduce((s, g) => s + Number(g.lng ?? g.lon ?? g.longitude), 0) / valid.length;
  return [lat, lng];
};

/** [lat, lng] for a gate, or null when the row has no usable coordinates. */
const gateCoords = (g: DeliveryGate): [number, number] | null => {
  const lat = g.lat ?? g.latitude;
  const lng = g.lng ?? g.lon ?? g.longitude;
  return typeof lat === 'number' && typeof lng === 'number' ? [lat, lng] : null;
};

// Custom pin / gate icons (divIcon avoids the broken default-marker asset issue).
const pinIcon = L.divIcon({
  className: 'hg-delivery-pin',
  html: '<div style="font-size:32px;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,.45));">📍</div>',
  iconSize: [32, 32],
  iconAnchor: [16, 32],
});
const gateIcon = L.divIcon({
  className: 'hg-delivery-gate',
  html: '<div style="font-size:22px;line-height:1;">🚪</div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});
const selectedGateIcon = L.divIcon({
  className: 'hg-delivery-gate-selected',
  html: '<div style="font-size:26px;line-height:1;filter:drop-shadow(0 0 6px #F72B13);">🚪</div>',
  iconSize: [26, 26],
  iconAnchor: [13, 13],
});

// Draggable user pin — reports its position on drag end.
function DraggablePin({ position, onDragEnd }) {
  return (
    <Marker
      position={position}
      icon={pinIcon}
      draggable
      eventHandlers={{
        dragend: (e) => {
          const ll = e.target.getLatLng();
          onDragEnd({ lat: ll.lat, lng: ll.lng });
        },
      }}
    />
  );
}

// Click-to-place — tapping the map moves the pin there.
function ClickHandler({ onClick }) {
  useMapEvents({
    click: (e) => onClick({ lat: e.latlng.lat, lng: e.latlng.lng }),
  });
  return null;
}

// Recenter the map when the pin jumps (e.g. GPS "use my location", or a search
// result). `nonce` forces the effect to re-run for a repeated coordinate.
function Recenter({ center, nonce }) {
  const map = useMap();
  useEffect(() => {
    if (center && center[0] != null) map.flyTo(center, 16, { duration: 0.8 });
  }, [center, nonce, map]);
  return null;
}

// Fix the "all-grey / blank tiles" bug. Leaflet must measure the container
// after it's fully visible and sized. We invalidate on ready, after several
// increasing delays (covers CSS transitions), and on every window resize.
function ResizeHandler() {
  const map = useMap();
  useEffect(() => {
    const invalidate = () => map.invalidateSize();
    // Staggered retries cover slow CSS transitions / lazy mount.
    const timers = [100, 300, 600, 1000].map((ms) => setTimeout(invalidate, ms));
    window.addEventListener('resize', invalidate);
    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener('resize', invalidate);
    };
  }, [map]);
  return null;
}

// ── Place search (OpenStreetMap Nominatim) ──────────────────────────────────
// The map is OpenStreetMap, so the search that belongs with it is OSM's own
// geocoder: no API key, no vendor swap, CORS-enabled from the browser.
// Nominatim's usage policy asks for at most one request per second and a
// meaningful Referer — the debounce below holds the rate down, and the requests
// only fire while the guest is typing a query.
const NOMINATIM_ENDPOINT = 'https://nominatim.openstreetmap.org/search';
const SEARCH_DEBOUNCE_MS = 700;
const SEARCH_MIN_CHARS = 3;

type PlaceHit = { id: string; label: string; lat: number; lng: number };

const shortenLabel = (label: string) => {
  const parts = label.split(',').map((p) => p.trim()).filter(Boolean);
  return parts.length > 1 ? `${parts[0]}, ${parts[parts.length - 1]}` : label;
};

const searchPlaces = async (query: string): Promise<PlaceHit[]> => {
  const url = `${NOMINATIM_ENDPOINT}?format=jsonv2&limit=5&countrycodes=ng&addressdetails=0&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`search failed (${res.status})`);
  const rows = await res.json();
  if (!Array.isArray(rows)) return [];
  return rows
    .map((r) => ({ id: String(r.place_id ?? r.osm_id ?? r.display_name), label: String(r.display_name || ''), lat: Number(r.lat), lng: Number(r.lon) }))
    .filter((r) => r.label && Number.isFinite(r.lat) && Number.isFinite(r.lng));
};

/**
 * OffCampusMap — OpenStreetMap with a place search, clickable gate markers, a
 * draggable delivery pin, GPS "use my location", and a live fee/distance
 * preview strip.
 *
 * Props:
 *  gates          — [{ id, name, lat, lng, base_fee, ... }]
 *  pin            — { lat, lng } | null
 *  onPinChange    — (latlng) => void
 *  selectedGateId — string | null
 *  onGateSelect   — (gate) => void
 *  feePreview     — { fee, km, gateName } | null   (computed by parent)
 *  center         — [lat, lng] the campus centre, so the map opens on the
 *                   campus instantly instead of waiting for the phone's GPS
 */
export default function OffCampusMap({
  gates = [],
  pin,
  onPinChange,
  selectedGateId,
  onGateSelect,
  feePreview,
  center = null,
}: {
  gates?: DeliveryGate[];
  pin?: { lat: number; lng: number } | null;
  onPinChange?: (pin: { lat: number; lng: number }) => void;
  selectedGateId?: string | null;
  onGateSelect?: (gate: DeliveryGate) => void;
  feePreview?: { fee?: number; km?: number; gateName?: string } | null;
  center?: [number, number] | null;
}) {
  // Campus centre first (opens instantly, no GPS wait), then the gate centroid,
  // then the last-resort Akure fallback.
  const view = center || centroid(gates);
  const [locating, setLocating] = useState(false);
  const [recenter, setRecenter] = useState(null);
  const [geoError, setGeoError] = useState('');
  const mapRef = useRef(null);

  // Place search state
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [searchError, setSearchError] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < SEARCH_MIN_CHARS) { setHits([]); setSearching(false); setSearchError(''); return; }
    setSearching(true);
    setSearchError('');
    // Nominatim's policy is one request/second — debounce to stay well under it
    // and to avoid a lookup for every keystroke.
    const t = setTimeout(() => {
      let alive = true;
      searchPlaces(q)
        .then((rows) => { if (alive) { setHits(rows); setSearchOpen(true); } })
        .catch(() => { if (alive) { setHits([]); setSearchError('Search is unavailable right now. Drop the pin manually instead.'); } })
        .finally(() => { if (alive) setSearching(false); });
      return () => { alive = false; };
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  const pickPlace = (hit: PlaceHit) => {
    onPinChange?.({ lat: hit.lat, lng: hit.lng });
    setRecenter([hit.lat, hit.lng]);
    setHits([]);
    setSearchOpen(false);
    setQuery('');
  };

  const handleUseLocation = () => {
    if (!navigator.geolocation) { setGeoError('GPS not supported. Drop the pin manually on the map.'); return; }
    setGeoError('');
    setLocating(true);
    // Diagnostic — trace the exact point where GPS values arrive or fail.
    const inIframe = (() => { try { return window.self !== window.top; } catch { return true; } })();
    // Low accuracy on purpose: the fee is computed from the nearest gate, not
    // from a metre-exact fix, and the high-accuracy request is what made the
    // first attempt hang on a phone with GPS still warming up. A cached fix up
    // to a minute old answers instantly and is plenty for picking a gate.
    const options = { enableHighAccuracy: false, timeout: 12000, maximumAge: 60000 };
    let retried = false;

    const onError = (err) => {
      // One automatic retry on a timeout — a cold GPS fix often succeeds on the
      // second ask, and the guest should not have to tap again.
      if (!retried && err?.code === 3) {
        retried = true;
        navigator.geolocation.getCurrentPosition(onSuccess, onError, options);
        return;
      }
      // eslint-disable-next-line no-console
      console.warn('[OffCampusMap] GPS error', { code: err?.code, message: err?.message, inIframe });
      setLocating(false);
      const msgs = {
        1: inIframe
          ? 'Location blocked by the preview frame — the app can\'t read GPS here. Drop the pin manually, or open the published app in its own tab.'
          : 'Location permission denied — enable it in your browser settings, or drop the pin manually.',
        2: 'Your location is unavailable right now — drop the pin manually on the map.',
        3: 'Location request timed out — try again, or drop the pin manually.',
      };
      setGeoError(err?.code ? (msgs[err.code] || `Could not get your location (error ${err.code}). Drop the pin manually.`) : 'Could not get your location — drop the pin manually on the map.');
    };

    const onSuccess = (pos) => {
      const ll = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      // eslint-disable-next-line no-console
      console.log('[OffCampusMap] GPS success', { lat: ll.lat, lng: ll.lng, accuracy: pos.coords.accuracy });
      // 1. Hand coordinates to the parent's existing location state.
      onPinChange?.(ll);
      // 2. Recenter the Leaflet map to the exact coordinates.
      setRecenter([ll.lat, ll.lng]);
      setLocating(false);
    };

    navigator.geolocation.getCurrentPosition(onSuccess, onError, options);
  };

  // Pin move only reports the new coordinates — the parent calls calculate-fee
  // and adopts the gate the backend returns (server-side nearest gate), instead
  // of pre-selecting a client-side nearest gate. Gate markers stay clickable for
  // a manual override.
  const handlePinMove = (ll) => {
    onPinChange?.(ll);
  };

  return (
    <div className="space-y-2">
      {/* Place search — for the guest who is NOT where the pin needs to be
          (ordering from school for delivery at home). */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => hits.length && setSearchOpen(true)}
          placeholder="Search a place, area or landmark…"
          aria-label="Search for a delivery location"
          className="w-full pl-9 pr-9 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
        />
        {searching ? (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
        ) : query ? (
          <button onClick={() => { setQuery(''); setHits([]); setSearchOpen(false); }} aria-label="Clear search" className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        ) : null}

        {searchOpen && hits.length > 0 && (
          <ul className="absolute z-[1000] left-0 right-0 mt-1 rounded-xl border border-border bg-card shadow-lg overflow-hidden max-h-56 overflow-y-auto">
            {hits.map((hit) => (
              <li key={hit.id}>
                <button
                  onClick={() => pickPlace(hit)}
                  className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-primary/10 transition-colors"
                >
                  <MapPin className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                  <span className="text-xs text-foreground leading-snug">{shortenLabel(hit.label)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {searchError && <p className="mt-1 text-[11px] text-primary font-semibold">{searchError}</p>}
      </div>

      <div className="rounded-2xl overflow-hidden border border-border relative" style={{ height: 300 }}>
        <MapContainer
          center={view}
          zoom={16}
          scrollWheelZoom={false}
          zoomControl
          style={{ height: '100%', width: '100%', zIndex: 0 }}
          ref={mapRef}
        >
          <ResizeHandler />
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
          {gates.map((g) => {
            const c = gateCoords(g);
            if (!c) return null;
            return (
              <Marker
                key={g.id}
                position={c}
                icon={selectedGateId === g.id ? selectedGateIcon : gateIcon}
                eventHandlers={{ click: () => onGateSelect(g) }}
              />
            );
          })}
          {pin && <DraggablePin position={[pin.lat, pin.lng]} onDragEnd={handlePinMove} />}
          <ClickHandler onClick={handlePinMove} />
          {recenter && <Recenter center={recenter} nonce={recenter.join(',')} />}
        </MapContainer>

        {/* Use-my-location overlay button */}
        <button
          type="button"
          onClick={handleUseLocation}
          disabled={locating}
          className="absolute top-3 right-3 z-[1000] flex items-center gap-1.5 px-3 py-2 rounded-full bg-white/95 border border-border shadow-md text-xs font-bold text-foreground active:scale-95 transition disabled:opacity-60"
        >
          {locating
            ? <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
            : <LocateFixed className="w-3.5 h-3.5 text-primary" />}
          {locating ? 'Locating…' : 'Use my location'}
        </button>
      </div>

      {geoError && (
        <p className="text-[11px] text-primary font-semibold flex items-center gap-1.5">
          <MapPin className="w-3 h-3 shrink-0" /> {geoError}
        </p>
      )}

      {/* Live fee / distance preview strip */}
      {pin ? (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-primary/10 border border-primary/20">
          <MapPin className="w-4 h-4 text-primary shrink-0" />
          <div className="flex-1 text-xs text-foreground">
            {feePreview ? (
              <>
                <span className="font-bold text-primary/90">₦{feePreview.fee?.toLocaleString?.() ?? feePreview.fee}</span>
                <span className="text-muted-foreground"> — {formatKm(feePreview.km)} from {feePreview.gateName || 'gate'}</span>
                <span className="block text-[11px] text-muted-foreground">Est. {etaLabel(feePreview.km)}</span>
              </>
            ) : (
              'Drag the pin to your exact spot'
            )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5" /> Tap the map, search a place, or use GPS to drop your delivery pin.
        </p>
      )}
    </div>
  );
}
