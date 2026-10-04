import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LocateFixed, MapPin } from 'lucide-react';
import { formatKm, etaLabel } from '@/lib/deliveryUtils';

// Centroid of the gates — used as the map's initial view.
const centroid = (gates) => {
  const valid = (gates || []).filter((g) => (g.lat ?? g.latitude) != null && (g.lng ?? g.lon ?? g.longitude) != null);
  if (!valid.length) return [7.295, 5.14]; // Akure fallback
  const lat = valid.reduce((s, g) => s + (g.lat ?? g.latitude), 0) / valid.length;
  const lng = valid.reduce((s, g) => s + (g.lng ?? g.lon ?? g.longitude), 0) / valid.length;
  return [lat, lng];
};

const gateCoords = (g) => [g.lat ?? g.latitude, g.lng ?? g.lon ?? g.longitude];

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

// Recenter the map when the pin jumps (e.g. GPS "use my location").
function Recenter({ center }) {
  const map = useMap();
  useEffect(() => {
    if (center && center[0] != null) map.flyTo(center, 16, { duration: 0.8 });
  }, [center, map]);
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

/**
 * OffCampusMap — OpenStreetMap with clickable gate markers, a draggable
 * delivery pin, GPS "use my location", and a live fee/distance preview strip.
 *
 * Props:
 *  gates          — [{ id, name, lat, lng, base_fee, ... }]
 *  pin            — { lat, lng } | null
 *  onPinChange    — (latlng) => void
 *  selectedGateId — string | null
 *  onGateSelect   — (gate) => void
 *  feePreview     — { fee, km, gateName } | null   (computed by parent)
 */
export default function OffCampusMap({ gates = [], pin, onPinChange, selectedGateId, onGateSelect, feePreview }) {
  const center = centroid(gates);
  const [locating, setLocating] = useState(false);
  const [recenter, setRecenter] = useState(null);
  const [geoError, setGeoError] = useState('');
  const mapRef = useRef(null);

  const handleUseLocation = () => {
    if (!navigator.geolocation) { setGeoError('GPS not supported. Drop the pin manually on the map.'); return; }
    setGeoError('');
    setLocating(true);
    // Diagnostic — trace the exact point where GPS values arrive or fail.
    const inIframe = (() => { try { return window.self !== window.top; } catch { return true; } })();
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const ll = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        // eslint-disable-next-line no-console
        console.log('[OffCampusMap] GPS success', { lat: ll.lat, lng: ll.lng, accuracy: pos.coords.accuracy });
        // 1. Hand coordinates to the parent's existing location state.
        onPinChange(ll);
        // 2. Recenter the Leaflet map to the exact coordinates.
        setRecenter([ll.lat, ll.lng]);
        setLocating(false);
      },
      (err) => {
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
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
    );
  };

  // Pin move only reports the new coordinates — the parent calls calculate-fee
  // and adopts the gate the backend returns (server-side nearest gate), instead
  // of pre-selecting a client-side nearest gate. Gate markers stay clickable for
  // a manual override.
  const handlePinMove = (ll) => {
    onPinChange(ll);
  };

  return (
    <div className="space-y-2">
      <div className="rounded-2xl overflow-hidden border border-border relative" style={{ height: 300 }}>
        <MapContainer
          center={center}
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
            if (c[0] == null || c[1] == null) return null;
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
          {recenter && <Recenter center={recenter} />}
        </MapContainer>

        {/* Use-my-location overlay button */}
        <button
          type="button"
          onClick={handleUseLocation}
          disabled={locating}
          className="absolute top-3 right-3 z-[1000] flex items-center gap-1.5 px-3 py-2 rounded-full bg-white/95 border border-border shadow-md text-xs font-bold text-foreground active:scale-95 transition disabled:opacity-60"
        >
          <LocateFixed className="w-3.5 h-3.5 text-primary" />
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
          <MapPin className="w-3.5 h-3.5" /> Tap the map or use GPS to drop your delivery pin.
        </p>
      )}
    </div>
  );
}