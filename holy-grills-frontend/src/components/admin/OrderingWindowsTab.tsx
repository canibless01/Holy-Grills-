import { useState, useEffect } from 'react';
import { Clock, Plus, Pencil, RefreshCw } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill } from './AdminShared';
import LoadingSpinner from '@/components/LoadingSpinner';
import { msg } from '@/lib/messages';

// Ordering Windows — when ordering is open each weekday/date, the per-slot
// capacity, and the delivery window a fulfilled order is linked to. A
// capacity increase can reassign deferred orders (handled server-side).
// Backend: GET/POST /admin/ordering-windows · PATCH /admin/ordering-windows/:id
// Backend expects weekday as an integer 0-6 (0=Monday). The select uses integer
// values so the raw form state can be sent to the backend without conversion.
const WEEKDAYS = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
];

export default function OrderingWindowsTab({ deliveryWindows = [] }) {
  const [windows, setWindows] = useState(null);
  const [modal, setModal] = useState(null); // { item?: {...} }
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setWindows(null);
    try { setWindows(await liveApi.admin.getOrderingWindows()); } catch (e) { toast({ title: msg('FE_ORDERING_WINDOWS_TAB_COULDN_T_LOAD_ORDERING_WINDOWS', "Couldn't load ordering windows"), description: e.message, variant: 'destructive' }); setWindows([]); }
  };
  useEffect(() => { load(); }, []);

  const save = async (item) => {
    setBusy(true);
    const payload = {
      label: item.label || null,
      weekday: item.weekday || null,
      date: item.date || null,
      opens_at: item.opens_at || null,
      closes_at: item.closes_at || null,
      capacity: item.capacity != null && item.capacity !== '' ? Number(item.capacity) : null,
      linked_delivery_window_id: item.linked_delivery_window_id || null,
      is_closed: !!item.is_closed,
    };
    try {
      if (item.id) await liveApi.admin.updateOrderingWindow(item.id, payload);
      else await liveApi.admin.createOrderingWindow(payload);
      setModal(null);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ORDERING_WINDOWS_TAB_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' });
    }
    setBusy(false);
  };

  if (windows == null) return <LoadingSpinner label="Loading ordering windows..." />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground flex items-center gap-1.5"><Clock className="w-4 h-4" /> When ordering is open, per weekday/date, with slot capacity.</div>
        <div className="flex gap-2">
          <button onClick={load} className="p-2 rounded-xl border border-border"><RefreshCw className="w-4 h-4 text-muted-foreground" /></button>
          <button onClick={() => setModal({ item: { weekday: 0, opens_at: '08:00', closes_at: '16:00', capacity: 100, is_closed: false } })} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> New Window</button>
        </div>
      </div>

      {windows.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground text-sm"><Clock className="w-8 h-8 mx-auto mb-2 text-muted-foreground" /> No ordering windows configured.</div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {windows.map((w) => {
            const closed = w.is_closed;
            return (
              <div key={w.id} className="rounded-2xl bg-white border border-border p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-sm text-foreground">{w.label || (w.weekday != null ? `${WEEKDAYS[w.weekday]?.label || `Day ${w.weekday}`}` : (w.date || 'Window'))}</span>
                  {closed ? <Pill tone="red">CLOSED</Pill> : <Pill tone="green">OPEN</Pill>}
                </div>
                <div className="text-xs text-muted-foreground mb-2">{w.opens_at && w.closes_at ? `${w.opens_at}–${w.closes_at}` : 'No hours set'}{w.date ? ` · ${w.date}` : ''}</div>
                <div className="flex items-center gap-2 text-xs mb-2"><span className="text-muted-foreground">Capacity</span><span className="font-bold text-foreground">{w.capacity ?? '∞'}</span></div>
                {w.linked_delivery_window_id && <div className="text-[11px] text-muted-foreground mb-2">Linked delivery: {deliveryWindows.find((d) => d.id === w.linked_delivery_window_id)?.label || w.linked_delivery_window_id.slice(0, 8)}</div>}
                <button onClick={() => setModal({ item: { ...w } })} className="w-full py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary flex items-center justify-center gap-1"><Pencil className="w-3 h-3" /> Edit</button>
              </div>
            );
          })}
        </div>
      )}

      {modal && <OrderingWindowModal item={modal.item} deliveryWindows={deliveryWindows} onClose={() => setModal(null)} onSave={save} busy={busy} />}
    </div>
  );
}

function OrderingWindowModal({ item, deliveryWindows, onClose, onSave, busy }) {
  const [form, setForm] = useState({
    label: item?.label || '',
    weekday: item?.weekday ?? '',
    date: item?.date || '',
    opens_at: item?.opens_at || '',
    closes_at: item?.closes_at || '',
    capacity: item?.capacity ?? '',
    linked_delivery_window_id: item?.linked_delivery_window_id || '',
    is_closed: item?.is_closed || false,
  });

  return (
    <Modal open onClose={onClose} title={item?.id ? 'Edit Ordering Window' : 'Create Ordering Window'}>
      <div className="space-y-3">
        <Field label="Label (optional)"><TextInput value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Lunch ordering" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Weekday">
            <select value={form.weekday ?? ''} onChange={(e) => setForm({ ...form, weekday: e.target.value === '' ? null : Number(e.target.value), date: '' })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
              <option value="">— None (use date) —</option>
              {WEEKDAYS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </Field>
          <Field label="Date (optional)"><TextInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value, weekday: '' })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Opens at"><TextInput type="time" value={form.opens_at} onChange={(e) => setForm({ ...form, opens_at: e.target.value })} /></Field>
          <Field label="Closes at"><TextInput type="time" value={form.closes_at} onChange={(e) => setForm({ ...form, closes_at: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Capacity (blank = ∞)"><TextInput type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} /></Field>
          <Field label="Linked delivery window">
            <select value={form.linked_delivery_window_id} onChange={(e) => setForm({ ...form, linked_delivery_window_id: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
              <option value="">— None —</option>
              {deliveryWindows.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </Field>
        </div>
        <label className="flex items-center gap-2 text-xs font-bold text-foreground">
          <input type="checkbox" checked={form.is_closed} onChange={(e) => setForm({ ...form, is_closed: e.target.checked })} className="w-4 h-4" />
          Mark as closed (overrides open hours)
        </label>
        <button onClick={() => onSave(form)} disabled={busy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </Modal>
  );
}