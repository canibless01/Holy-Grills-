import { useEffect, useRef, useState } from 'react';
import { LocateFixed, Search } from 'lucide-react';
import { loadGoogleMaps } from '@/lib/googleMaps';
import { formatKm, etaLabel } from '@/lib/deliveryUtils';
import type { DeliveryGate } from '@/types/delivery';

type Pin = { lat: number; lng: number };
type Props = {
  gates?: DeliveryGate[]; pin?: Pin | null; onPinChange?: (pin: Pin) => void;
  selectedGateId?: string | null; onGateSelect?: (gate: DeliveryGate) => void;
  feePreview?: { fee?: number; km?: number; gateName?: string } | null;
  center?: [number, number] | null;
};
const gatePin = (gate: DeliveryGate): Pin | null => {
  const lat = Number(gate.lat ?? gate.latitude), lng = Number(gate.lng ?? gate.lon ?? gate.longitude);
  return Number.isFinite(lat) && Number.isFinite(lng) && (gate.lat ?? gate.latitude) != null && (gate.lng ?? gate.lon ?? gate.longitude) != null ? { lat, lng } : null;
};

/** One basic Google map per visible checkout. Places loads only after a search.
 * No routing, Street View, 3D, reverse geocoding or custom styling requests.
 */
export default function OffCampusMap({ gates = [], pin, onPinChange, onGateSelect, selectedGateId, feePreview, center }: Props) {
  const element = useRef<HTMLDivElement>(null), map = useRef<any>(null), marker = useRef<any>(null);
  const gateMarkers = useRef<any[]>([]), session = useRef<any>(null), generation = useRef(0);
  const callbacks = useRef({ onPinChange, onGateSelect });
  callbacks.current = { onPinChange, onGateSelect };
  const [maps, setMaps] = useState<any>(null), [error, setError] = useState(''), [revision, setRevision] = useState(0);
  const [query, setQuery] = useState(''), [suggestions, setSuggestions] = useState<any[]>([]);
  const [searching, setSearching] = useState(false), [searchError, setSearchError] = useState('');
  const [locating, setLocating] = useState(false), [geoError, setGeoError] = useState('');
  const initial = center ? { lat: center[0], lng: center[1] } : gates.map(gatePin).find(Boolean) || { lat: 7.295, lng: 5.14 };

  useEffect(() => {
    let alive = true;
    setError('');
    loadGoogleMaps().then(async api => {
      const { Map } = await api.importLibrary('maps');
      if (!alive || !element.current) return;
      map.current = new Map(element.current, { center: pin || initial, zoom: pin ? 16 : 14, mapTypeId: 'roadmap',
        streetViewControl: false, mapTypeControl: false, fullscreenControl: false, clickableIcons: false, gestureHandling: 'cooperative' });
      map.current.addListener('click', (event: any) => {
        if (event.latLng) callbacks.current.onPinChange?.({ lat: event.latLng.lat(), lng: event.latLng.lng() });
      });
      setMaps(api);
    }).catch(() => { if (alive) setError('The map is unavailable. You can still use GPS, or choose a gate and enter your address below.'); });
    return () => {
      alive = false; generation.current++;
      const api = (window as any).google?.maps;
      if (map.current) api?.event?.clearInstanceListeners(map.current);
      marker.current?.setMap(null); marker.current = null;
      gateMarkers.current.forEach(item => item.setMap(null)); gateMarkers.current = [];
      map.current = null;
    };
  }, [revision]); // A pin move must not trigger another billable map load.

  useEffect(() => {
    if (!pin && map.current) map.current.setCenter(initial);
  }, [maps, center?.[0], center?.[1]]);

  useEffect(() => {
    if (!maps || !map.current || !pin) return;
    if (!marker.current) {
      marker.current = new maps.Marker({ map: map.current, position: pin, draggable: true, title: 'Your delivery pin' });
      marker.current.addListener('dragend', (event: any) => {
        if (event.latLng) callbacks.current.onPinChange?.({ lat: event.latLng.lat(), lng: event.latLng.lng() });
      });
    } else marker.current.setPosition(pin);
    map.current.panTo(pin);
  }, [maps, pin?.lat, pin?.lng]);

  useEffect(() => {
    if (!maps || !map.current) return;
    gateMarkers.current.forEach(item => item.setMap(null));
    gateMarkers.current = gates.filter(gate => gate.is_active !== false).flatMap(gate => {
      const position = gatePin(gate);
      if (!position) return [];
      const item = new maps.Marker({ map: map.current, position, title: gate.name, label: gate.id === selectedGateId ? '✓' : 'G' });
      item.addListener('click', () => callbacks.current.onGateSelect?.(gate));
      return [item];
    });
  }, [maps, gates, selectedGateId]);

  useEffect(() => {
    const version = ++generation.current;
    if (query.trim().length < 3) { setSuggestions([]); setSearching(false); return; }
    if (!maps) return;
    setSearchError(''); setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const places = await maps.importLibrary('places');
        session.current ||= new places.AutocompleteSessionToken();
        const response = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions({ input: query.trim(),
          sessionToken: session.current, includedRegionCodes: ['ng'], locationBias: { center: initial, radius: 50000 } });
        if (generation.current === version) setSuggestions(response.suggestions || []);
      } catch { if (generation.current === version) setSearchError('Search is unavailable. Tap the map or use GPS instead.'); }
      finally { if (generation.current === version) setSearching(false); }
    }, 600);
    return () => { clearTimeout(timer); };
  }, [query, maps]);

  const choose = async (suggestion: any) => {
    const version = ++generation.current;
    setSearching(true); setSuggestions([]);
    try {
      const place = suggestion.placePrediction.toPlace();
      await place.fetchFields({ fields: ['location', 'formattedAddress'] });
      if (generation.current !== version || !place.location) return;
      callbacks.current.onPinChange?.({ lat: place.location.lat(), lng: place.location.lng() });
      setQuery(''); session.current = null; map.current?.setZoom(16);
    } catch { if (generation.current === version) setSearchError('That location could not load. Tap the map or use GPS instead.'); }
    finally { if (generation.current === version) setSearching(false); }
  };
  const useLocation = () => {
    setGeoError('');
    if (!navigator.geolocation) { setGeoError('GPS is unavailable. Choose a gate and enter your address.'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(position => {
      setLocating(false); callbacks.current.onPinChange?.({ lat: position.coords.latitude, lng: position.coords.longitude }); map.current?.setZoom(16);
    }, () => { setLocating(false); setGeoError('Location access failed. Search, tap the map, or choose a gate and enter your address.'); },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  };

  return <div className="space-y-3">
    <div className="relative">
      <Search aria-hidden className="absolute left-3 top-3.5 w-4 h-4 text-muted-foreground" />
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search a place, area or landmark…" aria-label="Search delivery location" className="w-full border border-border rounded-2xl py-3 pl-10 pr-3 bg-card" />
      {searching && <p role="status" className="text-xs p-2">Searching…</p>}
      {suggestions.length > 0 && <ul className="absolute z-30 w-full bg-card border border-border rounded-xl shadow-lg max-h-60 overflow-auto">
        {suggestions.map((suggestion, index) => <li key={index}><button type="button" onClick={() => choose(suggestion)} className="w-full text-left p-3 text-sm hover:bg-muted">{suggestion.placePrediction?.text?.toString()}</button></li>)}
      </ul>}
      {searchError && <p role="status" className="text-xs text-destructive mt-1">{searchError}</p>}
    </div>
    {error && <div role="status" className="p-3 rounded-xl border border-border text-sm">{error}<button type="button" onClick={() => setRevision(value => value + 1)} className="block mt-2 font-bold text-primary underline">Retry map</button></div>}
    <div className="relative">
      <div ref={element} role="region" aria-label="Choose your delivery pin on Google Maps" className="h-[340px] sm:h-[380px] w-full rounded-2xl overflow-hidden bg-muted" />
      <button type="button" onClick={useLocation} disabled={locating} className="absolute top-3 right-3 flex items-center gap-2 bg-card rounded-full px-4 py-2 text-sm font-bold shadow"><LocateFixed className="w-4 h-4" />{locating ? 'Finding location…' : 'Use my location'}</button>
    </div>
    {geoError && <p role="status" className="text-sm text-destructive">{geoError}</p>}
    {pin && <p className="text-xs text-muted-foreground">Drag the pin or tap the map to adjust your delivery location.</p>}
    {feePreview?.fee != null && <div className="rounded-xl border border-primary/30 p-3 text-sm"><b>₦{feePreview.fee.toLocaleString()}</b>{feePreview.km != null && <> · {formatKm(feePreview.km)} from {feePreview.gateName}</>}{feePreview.km != null && <p className="text-xs text-muted-foreground">{etaLabel(feePreview.km)}</p>}</div>}
  </div>;
}
