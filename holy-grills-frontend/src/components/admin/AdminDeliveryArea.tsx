import { useState, useEffect, useCallback } from 'react';
import { MapPin, Save, Loader2, AlertTriangle, Ruler, ExternalLink } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import { useIsSuperAdmin } from './SuperAdminGate';
import { Card, Field, TextInput, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * Delivery area — the campus centre point + the delivery radius.
 * ============================================================================
 * The radius check is `is_within_delivery_area`: it measures the distance from
 * ONE point (the campus centre) and refuses anything beyond
 * `max_delivery_radius_km`. So "delivery range for my campus" is TWO values,
 * stored in two different places, and neither had an admin screen:
 *
 *   campuses.lat / campuses.lon
 *     GET/PATCH /admin/campuses/:id/location
 *     Accepts { coordinates: "7.3021, 5.1391" } pasted straight from Google
 *     Maps. Refuses coordinates outside Nigeria unless force: true.
 *
 *   kitchen_settings.max_delivery_radius_km   (per campus)
 *     GET/PATCH /kitchen/settings  →  { settings: { max_delivery_radius_km } }
 *     Campus scope is resolved server-side by _resolve_kitchen_campus_id(),
 *     so a campus admin writes their own campus without passing an id.
 *
 * Both are exposed by GET /storefront/config/public (campus_lat, campus_lon,
 * max_delivery_radius_km) which is what the checkout distance check uses.
 */

const DEFAULT_RADIUS_KM = 15;

// Accept either a pasted "7.3021, 5.1391" pair or two separate numbers.
const parseCoords = (raw) => {
  const parts = String(raw || '').replace(/,/g, ' ').split(/\s+/).filter(Boolean);
  if (parts.length !== 2) return null;
  const lat = Number(parts[0]);
  const lon = Number(parts[1]);
  if (!isFinite(lat) || !isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
};

export default function AdminDeliveryArea() {
  const { campuses, adminCampusId } = useCampus();
  const isSuperAdmin = useIsSuperAdmin();
  const [campusId, setCampusId] = useState(adminCampusId || '');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null); // 'location' | 'radius'
  const [coords, setCoords] = useState('');   // "lat, lon"
  const [radius, setRadius] = useState(String(DEFAULT_RADIUS_KM));
  const [saved, setSaved] = useState(null);   // last-known centre point
  const [error, setError] = useState(null);   // { text, canForce }

  const targetId = isSuperAdmin ? campusId : adminCampusId;
  const campusName = campuses.find((c) => c.id === targetId)?.name || 'this campus';

  const load = useCallback(async () => {
    if (!targetId) { setLoading(false); return; }
    setLoading(true);
    try {
      const [loc, ks] = await Promise.all([
        liveApi.admin.getCampusLocation(targetId).catch(() => null),
        liveApi.kitchen.getSettings().catch(() => ({})),
      ]);
      setSaved(loc && loc.lat != null && loc.lon != null ? { lat: loc.lat, lon: loc.lon } : null);
      setCoords(loc && loc.lat != null && loc.lon != null ? `${loc.lat}, ${loc.lon}` : '');
      const r = ks && ks.max_delivery_radius_km;
      setRadius(r != null && r !== '' ? String(r) : String(DEFAULT_RADIUS_KM));
      setError(null);
    } catch (e) {
      toast({ title: msg('FE_ADMIN_DELIVERY_AREA_COULDN_T_LOAD', "Couldn't load the delivery area"), description: e.message, variant: 'destructive' });
    }
    setLoading(false);
  }, [targetId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!campusId && adminCampusId) setCampusId(adminCampusId); }, [adminCampusId, campusId]);

  const saveLocation = async (force = false) => {
    if (!targetId) return;
    const parsed = parseCoords(coords);
    if (coords.trim() && !parsed) {
      setError({ text: msg('FE_ADMIN_DELIVERY_AREA_COORDS_INVALID', 'Enter coordinates as "latitude, longitude" — for example 7.3021, 5.1391'), canForce: false });
      return;
    }
    setSaving('location');
    setError(null);
    try {
      if (!parsed) {
        await liveApi.admin.setCampusLocation(targetId, { lat: null, lon: null });   // clear
        setSaved(null);
        toast({ title: msg('FE_ADMIN_DELIVERY_AREA_CENTRE_CLEARED', 'Campus centre cleared') });
      } else {
        const res = await liveApi.admin.setCampusLocation(targetId, { coordinates: `${parsed.lat}, ${parsed.lon}`, ...(force ? { force: true } : {}) });
        setSaved(parsed);
        toast({ title: msg('FE_ADMIN_DELIVERY_AREA_CENTRE_SAVED', 'Campus centre saved'), description: msg('FE_ADMIN_DELIVERY_AREA_DELIVERY_IS_MEASURED_FROM', 'Delivery distance is now measured from this point.') });
        if (res && res.map_url) setSaved({ ...parsed, map_url: res.map_url });
      }
      await load();
    } catch (e) {
      // The backend refuses points outside Nigeria unless force is set; offer
      // the override rather than dead-ending on a legitimate border campus.
      setError({ text: e?.message || msg('FE_ADMIN_DELIVERY_AREA_SAVE_FAILED', 'Could not save the campus centre'), canForce: !force });
      if (force) toast({ title: msg('FE_ADMIN_DELIVERY_AREA_FAILED', 'Failed'), description: e.message, variant: 'destructive' });
    }
    setSaving(null);
  };

  const saveRadius = async () => {
    const km = Number(radius);
    if (!isFinite(km) || km <= 0) {
      setError({ text: msg('FE_ADMIN_DELIVERY_AREA_RADIUS_INVALID', 'Radius must be a number greater than 0'), canForce: false });
      return;
    }
    setSaving('radius');
    setError(null);
    try {
      await liveApi.kitchen.updateSettings({ max_delivery_radius_km: String(km) });
      toast({ title: msg('FE_ADMIN_DELIVERY_AREA_RADIUS_SAVED', 'Delivery radius saved'), description: msg('FE_ADMIN_DELIVERY_AREA_RADIUS_SAVED_DESC', 'Orders beyond {km} km from the campus centre will be refused.', { km: km }) });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_DELIVERY_AREA_FAILED', 'Failed'), description: e.message, variant: 'destructive' });
    }
    setSaving(null);
  };

  const mapUrl = saved?.map_url || (saved ? `https://www.google.com/maps/search/?api=1&query=${saved.lat},${saved.lon}` : null);

  return (
    <div className="space-y-3">
      <Card className="p-4">
        <div className="flex items-start gap-2 mb-3">
          <MapPin className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-sm font-bold text-foreground">{msg('FE_ADMIN_DELIVERY_AREA_TITLE', 'Delivery area')}</p>
            <p className="text-[11px] text-muted-foreground break-words">
              {msg('FE_ADMIN_DELIVERY_AREA_SUBTITLE', 'Set the campus centre point and how far you deliver from it. Checkout refuses any address further away.')}
            </p>
          </div>
        </div>

        {isSuperAdmin && (
          <div className="mb-3">
            <Field label={msg('FE_ADMIN_DELIVERY_AREA_CAMPUS', 'Campus')}>
              <select value={campusId} onChange={(e) => setCampusId(e.target.value)}
                className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
                <option value="">{msg('FE_ADMIN_DELIVERY_AREA_SELECT_CAMPUS', 'Select a campus…')}</option>
                {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          </div>
        )}

        {!targetId ? (
          <p className="text-xs text-muted-foreground text-center py-6">{msg('FE_ADMIN_DELIVERY_AREA_PICK_CAMPUS', 'Pick a campus to edit its delivery area.')}</p>
        ) : loading ? (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> {msg('FE_ADMIN_DELIVERY_AREA_LOADING', 'Loading…')}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-muted-foreground">{msg('FE_ADMIN_DELIVERY_AREA_EDITING', 'Editing')}</span>
              <Pill tone="blue">{campusName}</Pill>
              {saved ? <Pill tone="green">{msg('FE_ADMIN_DELIVERY_AREA_CENTRE_SET', 'centre set')}</Pill> : <Pill tone="red">{msg('FE_ADMIN_DELIVERY_AREA_NO_CENTRE', 'no centre set')}</Pill>}
            </div>

            <Field label={msg('FE_ADMIN_DELIVERY_AREA_CENTRE_LABEL', 'Campus centre point')}
              hint={msg('FE_ADMIN_DELIVERY_AREA_CENTRE_HINT', 'Copy straight from Google Maps — right-click the spot and paste “latitude, longitude”. Leave empty to clear.')}>
              <TextInput value={coords} onChange={(e) => setCoords(e.target.value)} placeholder="7.3021, 5.1391" />
            </Field>

            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => saveLocation(false)} disabled={saving === 'location'}
                className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-95 transition">
                <Save className="w-3.5 h-3.5" /> {saving === 'location' ? msg('FE_ADMIN_DELIVERY_AREA_SAVING', 'Saving…') : msg('FE_ADMIN_DELIVERY_AREA_SAVE_CENTRE', 'Save centre point')}
              </button>
              {mapUrl && (
                <a href={mapUrl} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:text-primary transition">
                  <ExternalLink className="w-3.5 h-3.5" /> {msg('FE_ADMIN_DELIVERY_AREA_OPEN_IN_MAPS', 'Open in Maps')}
                </a>
              )}
            </div>

            <div className="border-t border-border pt-3">
              <Field label={msg('FE_ADMIN_DELIVERY_AREA_RADIUS_LABEL', 'Delivery radius (km)')}
                hint={msg('FE_ADMIN_DELIVERY_AREA_RADIUS_HINT', 'Measured from the centre point above. This is per campus — saved to kitchen_settings.max_delivery_radius_km.')}>
                <TextInput value={radius} onChange={(e) => setRadius(e.target.value)} inputMode="decimal" placeholder="15" />
              </Field>
              <button onClick={saveRadius} disabled={saving === 'radius'}
                className="mt-2 flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-95 transition">
                <Ruler className="w-3.5 h-3.5" /> {saving === 'radius' ? msg('FE_ADMIN_DELIVERY_AREA_SAVING', 'Saving…') : msg('FE_ADMIN_DELIVERY_AREA_SAVE_RADIUS', 'Save radius')}
              </button>
            </div>

            {error && (
              <div className="flex items-start gap-2 text-xs text-red-600 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span className="min-w-0 break-words">{error.text}</span>
              </div>
            )}
            {error?.canForce && (
              <button onClick={() => saveLocation(true)} disabled={saving === 'location'}
                className="text-xs font-bold text-primary hover:underline">
                {msg('FE_ADMIN_DELIVERY_AREA_SAVE_ANYWAY', 'These coordinates are outside Nigeria — save anyway')}
              </button>
            )}

            {!saved && !error && (
              <p className="text-[11px] text-amber-700 font-semibold break-words">
                {msg('FE_ADMIN_DELIVERY_AREA_NO_CENTRE_WARNING', 'Without a centre point every address is measured against nothing, so students get the 15 km default instead of your campus.')}
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
