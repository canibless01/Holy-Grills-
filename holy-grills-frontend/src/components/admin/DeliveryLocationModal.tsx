import { useRef, useState } from 'react';
import { Modal, Field, TextInput } from './AdminShared';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';

export default function DeliveryLocationModal({ type, item, gates, onClose, onSave, onDelete }) {
  const { user } = useHolyGrill();
  const { campuses, adminCampusId } = useCampus();
  const isGate = type === 'gate';
  const superAdmin = user?.role === 'super_admin';
  const ownCampus = user?.campus_id || user?.profile?.campus_id;
  const [form, setForm] = useState({ name: item?.name || '', campus_id: item ? (item.campus_id || '') : (superAdmin ? adminCampusId || '' : ownCampus || ''),
    delivery_fee: item ? String(item.delivery_fee ?? 0) : '', gate_id: item?.gate_id || '',
    base_fee: item ? String(item.base_fee ?? 0) : '', rate_per_km: String(item?.rate_per_km ?? 0), min_fee: item ? String(item.min_fee ?? 0) : '',
    lat: item?.lat == null ? '' : String(item.lat), lon: item?.lon == null ? '' : String(item.lon) });
  const [busy, setBusy] = useState(false);
  const writing = useRef(false);
  const change = (key, value) => setForm({ ...form, [key]: value, ...(key === 'campus_id' ? { gate_id: '' } : {}) });
  const close = () => { if (!writing.current) onClose(); };
  const submit = async () => {
    if (writing.current) return;
    let payload;
    try {
      if (!form.name.trim()) throw new Error(msg('FE_LOCATION_NAME_REQUIRED', 'Enter a location name.'));
      if (!item && !form.campus_id) throw new Error(msg('FE_LOCATION_CAMPUS_REQUIRED', 'Choose the campus for this delivery location.'));
      payload = { ...(item ? { id: item.id } : {}), name: form.name.trim(), ...(!item ? { campus_id: form.campus_id } : {}) };
      for (const key of isGate ? ['base_fee', 'rate_per_km', 'min_fee'] : ['delivery_fee']) {
        const value = Number(form[key]);
        if (form[key].trim() === '' || !Number.isFinite(value) || value < 0) throw new Error(msg('FE_LOCATION_FEE_INVALID', 'Enter a valid non-negative amount in every fee field.'));
        payload[key] = value;
      }
      if (isGate) {
        const hasLat = form.lat.trim() !== '', hasLon = form.lon.trim() !== '';
        const lat = Number(form.lat), lon = Number(form.lon);
        if (hasLat !== hasLon || (hasLat && (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < 4 || lat > 14 || lon < 2.5 || lon > 15))) throw new Error(msg('FE_LOCATION_COORDINATES_INVALID', 'Enter both latitude and longitude within Nigeria, or leave both blank.'));
        payload.lat = hasLat ? lat : null; payload.lon = hasLon ? lon : null;
      } else payload.gate_id = form.gate_id || null;
    } catch (error) { toast({ title: error.message, variant: 'destructive' }); return; }
    writing.current = true; setBusy(true);
    try { await onSave(type, payload); }
    catch (error) { toast({ title: msg('FE_LOCATION_SAVE_FAILED', 'Delivery location could not be saved.'), description: error.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(false); }
  };
  const hide = async () => {
    if (writing.current) return;
    writing.current = true; setBusy(true);
    try { await onDelete(type, item.id); }
    catch (error) { toast({ title: msg('FE_LOCATION_SAVE_FAILED', 'Delivery location could not be saved.'), description: error.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(false); }
  };
  const selectableGates = (gates || []).filter((gate) => gate.is_active !== false && (gate.campus_id || '') === form.campus_id);
  return <Modal open onClose={close} title={isGate ? msg('FE_LOCATION_GATE', 'Delivery gate') : msg('FE_LOCATION_HOSTEL', 'Delivery hostel')}>
    <fieldset disabled={busy} className="space-y-3">
      <Field label={msg('FE_LOCATION_CAMPUS', 'Campus')}><select disabled={!!item || !superAdmin} value={superAdmin ? form.campus_id : ownCampus || ''} onChange={(event) => change('campus_id',event.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm">
        <option value="">{msg('FE_LOCATION_SELECT_CAMPUS', 'Choose a campus')}</option>
        {form.campus_id && !campuses.some(campus => campus.id === form.campus_id) && <option value={form.campus_id}>{msg('FE_LOCATION_CURRENT_CAMPUS', 'Current campus')}</option>}
        {campuses.filter(campus => superAdmin || campus.id === ownCampus).map(campus => <option key={campus.id} value={campus.id}>{campus.name}</option>)}
      </select></Field>
      <Field label={msg('FE_LOCATION_NAME', 'Name')}><TextInput value={form.name} onChange={(event) => change('name',event.target.value)} /></Field>
      {isGate ? <>
        <Field label={msg('FE_LOCATION_BASE_FEE', 'Base fee (₦)')}><TextInput type="number" min="0" step="0.01" value={form.base_fee} onChange={(event) => change('base_fee',event.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_LOCATION_RATE', 'Rate per km (₦)')}><TextInput type="number" min="0" step="0.01" value={form.rate_per_km} onChange={(event) => change('rate_per_km',event.target.value)} /></Field>
          <Field label={msg('FE_LOCATION_MIN_FEE', 'Minimum fee (₦)')}><TextInput type="number" min="0" step="0.01" value={form.min_fee} onChange={(event) => change('min_fee',event.target.value)} /></Field>
        </div>
        <p className="text-xs text-muted-foreground">{msg('FE_LOCATION_FEE_HELP', 'With a map pin: base fee plus distance × rate, at least the minimum fee. Without a pin: the greater of the base and minimum fee.')}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_LOCATION_LATITUDE', 'Latitude')}><TextInput type="number" step="any" value={form.lat} onChange={(event) => change('lat',event.target.value)} /></Field>
          <Field label={msg('FE_LOCATION_LONGITUDE', 'Longitude')}><TextInput type="number" step="any" value={form.lon} onChange={(event) => change('lon',event.target.value)} /></Field>
        </div>
      </> : <>
        <Field label={msg('FE_LOCATION_DELIVERY_FEE', 'Delivery fee (₦)')}><TextInput type="number" min="0" step="0.01" value={form.delivery_fee} onChange={(event) => change('delivery_fee',event.target.value)} /></Field>
        <Field label={msg('FE_LOCATION_NEAREST_GATE', 'Nearest gate (optional)')}><select value={form.gate_id} onChange={(event) => change('gate_id',event.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm">
          <option value="">{msg('FE_LOCATION_NO_GATE', 'No gate link')}</option>
          {form.gate_id && !selectableGates.some(gate => gate.id === form.gate_id) && <option disabled value={form.gate_id}>{msg('FE_LOCATION_OLD_GATE', 'Previous gate unavailable — choose another or clear')}</option>}
          {selectableGates.map(gate => <option key={gate.id} value={gate.id}>{gate.name}</option>)}
        </select></Field>
      </>}
      <div className="flex gap-2">
        <button onClick={submit} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold">{busy ? msg('FE_LOCATION_SAVING', 'Saving…') : msg('FE_LOCATION_SAVE', 'Save')}</button>
        {item && item.is_active !== false && <button onClick={hide} className="px-4 py-3 rounded-full tone-error border border-destructive/30 font-bold">{msg('FE_LOCATION_HIDE', 'Hide')}</button>}
      </div>
    </fieldset>
  </Modal>;
}
