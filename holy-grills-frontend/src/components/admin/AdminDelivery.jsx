import React, { useState, useEffect } from 'react';
import { Calendar, Truck, ShoppingCart, Send, Plus, MapPin, Home, Trash2, X, Pencil, CheckSquare, Clock, Bike } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatDateTime, formatNaira, timeAgo, formatDate } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Modal, Field, TextInput, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import OrderingWindowsTab from './OrderingWindowsTab';
import AdminRiders from './AdminRiders';

export default function AdminDelivery() {
  const [tab, setTab] = useState('windows');
  const [windows, setWindows] = useState([]);
  const [batches, setBatches] = useState([]);
  const [carts, setCarts] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [gates, setGates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [showCreateWindow, setShowCreateWindow] = useState(false);
  const [editWindow, setEditWindow] = useState(null);
  const [batchModal, setBatchModal] = useState(false);
  const [batchBusy, setBatchBusy] = useState(null);
  const [zoneModal, setZoneModal] = useState(null); // {type:'hostel'|'gate', item?:...}

  const load = async () => {
    setLoading(true);
    const [w, b, c, h, g] = await Promise.all([
      mockApi.admin.getDeliveryWindows(),
      mockApi.admin.getDeliveryBatches(),
      mockApi.admin.getAbandonedCarts(),
      mockApi.admin.getDeliveryHostels(),
      mockApi.admin.getDeliveryGates(),
    ]);
    setWindows(w); setBatches(b); setCarts(c); setHostels(h); setGates(g);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const handleWindow = async (id, action) => {
    setBusy(id);
    if (action === 'close') await mockApi.admin.closeWindow(id);
    else await mockApi.admin.reopenWindow(id);
    await load();
    setBusy(null);
  };

  const handleNudge = async (id) => { setBusy(id); await mockApi.admin.nudgeAbandonedCart(id); await load(); setBusy(null); };

  const completeBatch = async (id) => { setBatchBusy(id); try { await mockApi.admin.updateDeliveryBatch(id, { status: 'completed' }); toast({ title: '✅ Batch completed' }); await load(); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } setBatchBusy(null); };
  const cancelBatch = async (id) => { if (!confirm('Cancel this batch? Its orders will be unassigned.')) return; setBatchBusy(id); try { await mockApi.admin.deleteDeliveryBatch(id); toast({ title: 'Batch cancelled' }); await load(); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } setBatchBusy(null); };

  const saveZone = async (type, item) => {
    if (item && item.id) {
      if (type === 'hostel') await mockApi.admin.updateDeliveryHostel(item.id, item);
      else await mockApi.admin.updateDeliveryGate(item.id, item);
    } else if (item) {
      if (type === 'hostel') await mockApi.admin.createDeliveryHostel(item);
      else await mockApi.admin.createDeliveryGate(item);
    }
    setZoneModal(null);
    await load();
  };

  const deleteZone = async (type, id) => {
    try {
      if (type === 'hostel') await mockApi.admin.deleteDeliveryHostel(id);
      else await mockApi.admin.deleteDeliveryGate(id); // soft-deactivates (is_active=false)
      toast({ title: type === 'hostel' ? '✅ Hostel deleted' : '⏸ Gate deactivated', description: type === 'hostel' ? 'Hostel removed.' : 'Gate is hidden from students and existing orders keep their reference. Restore it any time.' });
      setZoneModal(null);
      await load();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  const restoreGate = async (id) => {
    try { await mockApi.admin.restoreDeliveryGate(id); toast({ title: '✅ Gate restored', description: 'Gate is active and visible to students again.' }); await load(); }
    catch (e) { toast({ title: 'Restore failed', description: e.message, variant: 'destructive' }); }
  };

  if (loading) return <LoadingSpinner label="Loading delivery..." />;

  const tabs = [
    { id: 'windows', label: 'Windows', icon: Calendar },
    { id: 'ordering', label: 'Ordering', icon: Clock },
    { id: 'batches', label: 'Batches', icon: Truck },
    { id: 'zones', label: 'Zones & Fees', icon: MapPin },
    { id: 'riders', label: 'Riders', icon: Bike },
    { id: 'carts', label: 'Abandoned', icon: ShoppingCart },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center justify-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition ${tab === t.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card border border-border text-muted-foreground hover:text-foreground'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {tab === 'windows' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setShowCreateWindow(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> New Window</button>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {windows.map((w) => (
              <div key={w.id} className="rounded-2xl bg-card border border-border shadow-card p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-sm text-foreground">{w.label}</span>
                  <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${w.status === 'open' ? 'bg-green-100 text-green-600' : 'bg-blue-100 text-blue-600'}`}>{w.status.toUpperCase()}</span>
                </div>
                <div className="text-xs text-muted-foreground mb-2">{formatDateTime(w.starts_at)}</div>
                <div className="flex items-center gap-2 text-xs mb-2"><span className="text-muted-foreground">Cap {w.capacity}</span><span className="font-bold text-foreground">{w.order_count ?? w.orders_count ?? 0} orders</span></div>
                <div className="w-full h-1.5 rounded-full bg-secondary mb-3"><div className="h-full rounded-full bg-gradient-cta" style={{ width: `${Math.min(100, ((w.order_count ?? w.orders_count ?? 0) / Math.max(1, w.capacity || 1)) * 100)}%` }} /></div>
                <div className="flex gap-2">
                  <button onClick={() => setEditWindow(w)} className="flex-1 py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary transition">
                    <Pencil className="w-3 h-3 inline mr-1" />Edit
                  </button>
                  <button onClick={() => handleWindow(w.id, w.status === 'open' ? 'close' : 'reopen')} disabled={busy === w.id}
                    className={`flex-1 py-2 rounded-full text-xs font-bold disabled:opacity-50 ${w.status === 'open' ? 'bg-red-50 text-red-600 border border-red-200' : 'bg-green-50 text-green-600 border border-green-200'}`}>
                    {w.status === 'open' ? 'Close' : 'Reopen'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'ordering' && (
        <OrderingWindowsTab deliveryWindows={windows} />
      )}

      {tab === 'batches' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={() => setBatchModal(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> New Batch</button>
          </div>
          {batches.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-sm"><Truck className="w-8 h-8 mx-auto mb-2 text-muted-foreground" /> No delivery batches yet.</div>
          ) : batches.map((b) => (
            <div key={b.id} className="rounded-2xl bg-card border border-border shadow-card p-4">
              <div className="flex items-center justify-between mb-2">
                <div><div className="font-bold text-sm text-foreground">{b.zone}</div><div className="text-xs text-muted-foreground font-mono">#{b.id.toUpperCase()}</div></div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full capitalize ${b.status === 'out_for_delivery' ? 'bg-blue-100 text-blue-600' : b.status === 'assigned' ? 'bg-amber-100 text-amber-600' : b.status === 'completed' ? 'bg-green-100 text-green-600' : 'bg-secondary text-muted-foreground'}`}>{b.status.replace(/_/g, ' ')}</span>
              </div>
              <div className="flex items-center justify-between text-xs"><span className="text-muted-foreground">Rider: {b.profiles?.full_name || b.rider_name || <span className="text-red-500">Unassigned</span>}</span><span className="font-bold text-foreground">{b.order_count ?? 0} orders</span></div>
              {b.status !== 'completed' && b.status !== 'cancelled' && (
                <div className="flex gap-2 mt-2">
                  <button onClick={() => completeBatch(b.id)} disabled={batchBusy === b.id} className="flex-1 py-1.5 rounded-full bg-green-600 text-white text-xs font-bold disabled:opacity-50">{batchBusy === b.id ? '...' : 'Mark Completed'}</button>
                  <button onClick={() => cancelBatch(b.id)} disabled={batchBusy === b.id} className="px-3 py-1.5 rounded-full bg-red-50 text-red-600 border border-red-200 text-xs font-bold disabled:opacity-50">Cancel</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === 'zones' && (
        <div className="space-y-5">
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-sm text-foreground flex items-center gap-1.5"><Home className="w-4 h-4 text-primary" /> On-Campus Hostels</h3>
              <button onClick={() => setZoneModal({ type: 'hostel' })} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-3 h-3" /> Add</button>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {hostels.map((h) => (
                <div key={h.id} className="rounded-xl bg-card border border-border p-3 flex items-center gap-2 shadow-card">
                  <MapPin className="w-4 h-4 text-primary shrink-0" />
                  <div className="flex-1 min-w-0"><div className="font-bold text-xs text-foreground truncate">{h.name}</div><div className="text-[11px] text-muted-foreground">Fee {formatNaira(h.delivery_fee)}</div></div>
                  <button onClick={() => setZoneModal({ type: 'hostel', item: h })} className="p-1.5 rounded-lg hover:bg-secondary"><Pencil className="w-3.5 h-3.5 text-muted-foreground" /></button>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-sm text-foreground flex items-center gap-1.5"><MapPin className="w-4 h-4 text-blue-600" /> Off-Campus Gates</h3>
              <button onClick={() => setZoneModal({ type: 'gate' })} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-3 h-3" /> Add</button>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {gates.map((g) => {
                const isActive = g.is_active !== false;
                return (
                <div key={g.id} className={`rounded-xl bg-card border p-3 shadow-card ${isActive ? 'border-border' : 'border-border opacity-75'}`}>
                  <div className="flex items-center gap-2">
                    <MapPin className={`w-4 h-4 shrink-0 ${isActive ? 'text-blue-500' : 'text-muted-foreground'}`} />
                    <div className="flex-1 min-w-0"><div className="font-bold text-xs text-foreground truncate">{g.name}</div><div className="text-[11px] text-muted-foreground">Base fee {formatNaira(g.base_fee)}</div></div>
                    {isActive ? <Pill tone="green">Active</Pill> : <Pill tone="red">Deactivated</Pill>}
                    <button onClick={() => setZoneModal({ type: 'gate', item: g })} className="p-1.5 rounded-lg hover:bg-secondary"><Pencil className="w-3.5 h-3.5 text-muted-foreground" /></button>
                  </div>
                  {!isActive && (
                    <button onClick={() => restoreGate(g.id)} className="mt-2 w-full px-3 py-1.5 rounded-full bg-green-50 text-green-600 border border-green-200 text-[11px] font-bold">Restore gate</button>
                  )}
                </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {tab === 'riders' && <AdminRiders />}

      {tab === 'carts' && (
        <div className="space-y-2">
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs text-amber-700"><ShoppingCart className="w-4 h-4 inline mr-1" /> Carts inactive for 60+ minutes. Send a recovery nudge to bring them back.</div>
          {carts.map((c) => (
            <div key={c.id} className="rounded-2xl bg-card border border-border shadow-card p-3 flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${c.nudged ? 'bg-amber-50' : 'bg-primary/10'}`}><ShoppingCart className={`w-5 h-5 ${c.nudged ? 'text-amber-500' : 'text-primary'}`} /></div>
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{c.profiles?.full_name || c.user_name || 'User'}</div><div className="text-xs text-muted-foreground">{c.item_count ?? (Array.isArray(c.items) ? c.items.length : 0)} items · {formatNaira(c.total_value ?? c.subtotal ?? c.total ?? 0)} · last activity {timeAgo(c.last_active_at || c.last_activity || c.updated_at)}</div></div>
              {(c.recovery_attempts ?? 0) > 0 ? <span className="text-[10px] font-bold text-amber-600 bg-amber-50 px-2 py-1 rounded-full">Nudged</span>
                : <button onClick={() => handleNudge(c.id)} disabled={busy === c.id} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Send className="w-3 h-3" />Nudge</button>}
            </div>
          ))}
        </div>
      )}

      {showCreateWindow && <CreateWindowModal onClose={() => setShowCreateWindow(false)} onSaved={load} />}
      {editWindow && <CreateWindowModal window={editWindow} onClose={() => setEditWindow(null)} onSaved={load} />}
      {batchModal && <CreateBatchModal windows={windows} onClose={() => setBatchModal(false)} onSaved={load} />}
      {zoneModal && <ZoneModal type={zoneModal.type} item={zoneModal.item} onClose={() => setZoneModal(null)} onSave={saveZone} onDelete={deleteZone} />}
    </div>
  );
}

function CreateWindowModal({ window: existing, onClose, onSaved }) {
  const editing = !!existing;
  // Pre-fill from the existing window when editing. The backend stores starts_at/ends_at
  // as ISO instants; datetime-local inputs need the local-time slice (first 16 chars).
  const toLocal = (iso) => iso ? new Date(iso).toISOString().slice(0, 16) : '';
  const [form, setForm] = useState(existing
    ? { label: existing.label || '', starts_at: toLocal(existing.starts_at), ends_at: toLocal(existing.ends_at), capacity: existing.capacity ?? 50 }
    : { label: '', starts_at: '', ends_at: '', capacity: 50 });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!form.ends_at) { toast({ title: 'End time required', variant: 'destructive' }); return; }
    if (form.starts_at && form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)) { toast({ title: 'End time must be after the start time', variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      const payload = {
        label: form.label,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        capacity: Number(form.capacity),
      };
      if (editing) {
        await mockApi.admin.updateDeliveryWindow(existing.id, payload);
        toast({ title: '✅ Window updated' });
      } else {
        await mockApi.admin.createDeliveryWindow(payload);
      }
      onClose(); onSaved();
    } catch (e) { toast({ title: editing ? 'Failed to update window' : 'Failed to create window', description: e.message, variant: 'destructive' }); }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={editing ? 'Edit Delivery Window' : 'Create Delivery Window'}>
      <div className="space-y-3">
        <Field label="Label"><TextInput value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Morning Window" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts at"><input type="datetime-local" value={form.starts_at} onChange={(e) => setForm({ ...form, starts_at: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
          <Field label="Ends at"><input type="datetime-local" value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
        </div>
        <Field label="Capacity"><TextInput type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} /></Field>
        <button onClick={submit} disabled={submitting || !form.label || !form.starts_at || !form.ends_at} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? (editing ? 'Saving...' : 'Creating...') : (editing ? 'Save Changes' : 'Create Window')}</button>
      </div>
    </Modal>
  );
}

function CreateBatchModal({ windows, onClose, onSaved }) {
  const [windowId, setWindowId] = useState(windows[0]?.id || '');
  const [riderId, setRiderId] = useState('');
  const [zone, setZone] = useState('');
  const [riders, setRiders] = useState([]);
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try { const r = await mockApi.admin.getUsers({ role: 'rider' }); setRiders(r || []); } catch { setRiders([]); }
      try { const o = await mockApi.admin.getAdminOrders({ status: 'ready' }); setOrders(o || []); } catch { setOrders([]); }
    })();
  }, []);

  const toggle = (id) => { const n = new Set(selected); if (n.has(id)) n.delete(id); else n.add(id); setSelected(n); };

  const submit = async () => {
    if (!windowId || !riderId || !zone) { toast({ title: 'Missing fields', description: 'Window, rider and zone are all required.', variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      await mockApi.admin.createDeliveryBatch({ window_id: windowId, rider_id: riderId, zone, order_ids: [...selected] });
      toast({ title: '✅ Batch created', description: `${selected.size} order(s) assigned.` });
      onSaved(); onClose();
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title="Create Delivery Batch">
      <div className="space-y-3">
        <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">A batch groups orders for one rider in one zone under a delivery window. Assigned orders move to <b>assigned</b> status.</div>
        <Field label="Delivery Window">
          <select value={windowId} onChange={(e) => setWindowId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            <option value="">Select window…</option>
            {windows.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
          </select>
        </Field>
        <Field label="Rider">
          <select value={riderId} onChange={(e) => setRiderId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            <option value="">Select rider…</option>
            {riders.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}
          </select>
        </Field>
        <Field label="Zone"><TextInput value={zone} onChange={(e) => setZone(e.target.value)} placeholder="e.g. North Gate" /></Field>
        <Field label="Assign Orders (optional)">
          <div className="max-h-48 overflow-y-auto rounded-xl border border-border mt-1">
            {orders.length === 0 ? <div className="p-3 text-xs text-muted-foreground">No ready orders available to assign.</div> : orders.map((o) => (
              <button key={o.id} type="button" onClick={() => toggle(o.id)} className={`w-full text-left p-2.5 flex items-center gap-2 border-b border-border last:border-0 ${selected.has(o.id) ? 'bg-primary/10' : 'hover:bg-muted'}`}>
                <span className="text-xs font-mono text-muted-foreground">#{o.id.slice(0, 6).toUpperCase()}</span>
                <span className="text-xs text-muted-foreground truncate flex-1">{(o.order_items || []).map((it) => `${it.quantity}× ${it.name_snapshot || it.name}`).join(', ')}</span>
                {selected.has(o.id) && <CheckSquare className="w-3.5 h-3.5 text-primary shrink-0" />}
              </button>
            ))}
          </div>
        </Field>
        <button onClick={submit} disabled={submitting || !windowId || !riderId || !zone} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? 'Creating...' : 'Create Batch'}</button>
      </div>
    </Modal>
  );
}

function ZoneModal({ type, item, onClose, onSave, onDelete }) {
  const [form, setForm] = useState(item ? { ...item } : { name: '', ...(type === 'hostel' ? { delivery_fee: 300 } : { base_fee: 400, lat: 7.30, lon: 5.13 }) });
  const feeKey = type === 'hostel' ? 'delivery_fee' : 'base_fee';
  return (
    <Modal open onClose={onClose} title={`${item ? 'Edit' : 'Add'} ${type === 'hostel' ? 'Hostel' : 'Gate'}`}>
      <div className="space-y-3">
        <Field label="Name"><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label={type === 'hostel' ? 'Delivery fee (₦)' : 'Base fee (₦)'}><TextInput type="number" value={form[feeKey]} onChange={(e) => setForm({ ...form, [feeKey]: Number(e.target.value) })} /></Field>
        {type === 'hostel' && (
          <Field label="Gate ID (optional)"><TextInput value={form.gate_id || ''} onChange={(e) => setForm({ ...form, gate_id: e.target.value })} /></Field>
        )}
        {type === 'gate' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Latitude"><TextInput type="number" value={form.lat} onChange={(e) => setForm({ ...form, lat: Number(e.target.value) })} /></Field>
            <Field label="Longitude"><TextInput type="number" value={form.lon} onChange={(e) => setForm({ ...form, lon: Number(e.target.value) })} /></Field>
          </div>
        )}
        <div className="flex gap-2">
          <button onClick={() => onSave(type, form)} disabled={!form.name} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">Save</button>
          {item && <button onClick={() => onDelete(type, item.id)} className="px-4 py-3 rounded-full bg-red-50 text-red-600 border border-red-200 font-bold"><Trash2 className="w-4 h-4" /></button>}
        </div>
      </div>
    </Modal>
  );
}