import CapacityGuide from './CapacityGuide';
import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect } from 'react';
import { Calendar, Truck, ShoppingCart, Send, Plus, MapPin, Home, Trash2, Pencil, Clock, Bike } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatDateTime, formatNaira, timeAgo } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Modal, Field, TextInput, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import OrderingWindowsTab from './OrderingWindowsTab';
import CreateBatchModal from './AdminCreateBatchModal';
import AdminManageBatchModal from './AdminManageBatchModal';
import AdminRiders from './AdminRiders';
import AdminDeliveryArea from './AdminDeliveryArea';
import { msg } from '@/lib/messages';

export default function AdminDelivery() {
  const [tab, setTab] = useState('batches');
  const [windows, setWindows] = useState([]);
  const [batches, setBatches] = useState([]);
  const [carts, setCarts] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [gates, setGates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(null);
  const [showCreateWindow, setShowCreateWindow] = useState(false);
  const [editWindow, setEditWindow] = useState(null);
  const [batchModal, setBatchModal] = useState(false);
  const [manageBatch, setManageBatch] = useState(null);
  const [batchBusy, setBatchBusy] = useState(null);
  const [zoneModal, setZoneModal] = useState(null); // {type:'hostel'|'gate', item?:...}

  const load = async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      mockApi.admin.getDeliveryWindows(), mockApi.admin.getDeliveryBatches(),
      mockApi.admin.getAbandonedCarts(), mockApi.admin.getDeliveryHostels(), mockApi.admin.getDeliveryGates(),
    ]);
    const setters = [setWindows, setBatches, setCarts, setHostels, setGates];
    results.forEach((result, index) => { if (result.status === 'fulfilled') setters[index](result.value || []); });
    setLoadError(results.some(result => result.status === 'rejected')
      ? msg('FE_BATCH_LOAD_RETRY', 'Some delivery data could not be loaded. Retry to refresh it.') : '');
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

  const completeBatch = async (id) => { setBatchBusy(id); try { await mockApi.admin.updateDeliveryBatch(id, { status: 'completed' }); toast({ title: msg('FE_ADMIN_DELIVERY_BATCH_COMPLETED', '✅ Batch completed') }); await load(); } catch (e) { toast({ title: msg('FE_ADMIN_DELIVERY_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); } setBatchBusy(null); };
  const cancelBatch = async (id) => { if (!(await confirmAction({ title: "Cancel this batch?", body: "Its orders will be unassigned.", destructive: true, confirmLabel: "Cancel" }))) return; setBatchBusy(id); try { await mockApi.admin.deleteDeliveryBatch(id); toast({ title: msg('FE_ADMIN_DELIVERY_BATCH_CANCELLED', 'Batch cancelled') }); await load(); } catch (e) { toast({ title: msg('FE_ADMIN_DELIVERY_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); } setBatchBusy(null); };

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
      toast({ title: msg('FE_ADMIN_DELIVERY_DELETE_FAILED', 'Delete failed'), description: e.message, variant: 'destructive' });
    }
  };

  const restoreGate = async (id) => {
    try { await mockApi.admin.restoreDeliveryGate(id); toast({ title: msg('FE_ADMIN_DELIVERY_GATE_RESTORED', '✅ Gate restored'), description: msg('FE_ADMIN_DELIVERY_GATE_IS_ACTIVE_AND_VISIBLE_TO_STUDENTS', 'Gate is active and visible to students again.') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_DELIVERY_RESTORE_FAILED', 'Restore failed'), description: e.message, variant: 'destructive' }); }
  };

  if (loading) return <StaffPanelSkeleton />;

  const tabs = [
    { id: 'windows', label: msg('FE_CAPACITY_DELIVERY_TIMES', 'Delivery times'), icon: Calendar },
    { id: 'ordering', label: msg('FE_CAPACITY_ORDERING_TIMES', 'Ordering & slots'), icon: Clock },
    { id: 'batches', label: 'Batches', icon: Truck },
    { id: 'zones', label: 'Zones & Fees', icon: MapPin },
    { id: 'area', label: 'Delivery area', icon: MapPin },
    { id: 'riders', label: 'Riders', icon: Bike },
    { id: 'carts', label: 'Abandoned', icon: ShoppingCart },
  ];

  return (
    <div className="space-y-4">
      {loadError && <div role="alert" className="rounded-xl border border-destructive/30 p-3 text-sm text-destructive">{loadError} <button onClick={load} className="underline">{msg('FE_BATCH_RETRY', 'Retry')}</button></div>}
      {(tab === 'windows' || tab === 'ordering') && <CapacityGuide />}
      <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center justify-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition ${tab === t.id ? 'bg-primary text-primary-foreground' : 'bg-card border border-border text-muted-foreground hover:text-foreground'}`}>
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
                  <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${w.status === 'open' ? 'tone-success' : 'tone-info'}`}>{w.status.toUpperCase()}</span>
                </div>
                <div className="text-xs text-muted-foreground mb-2">{formatDateTime(w.starts_at)}</div>
                <div className="flex items-center gap-2 text-xs mb-2"><span className="text-muted-foreground">{msg('FE_CAPACITY_PLANNING_VALUE', 'Planning target: {count}', { count: w.capacity ?? '—' })}</span><span className="font-bold text-foreground">{w.order_count ?? w.orders_count ?? 0} orders</span></div>
                <div className="w-full h-1.5 rounded-full bg-secondary mb-3"><div className="h-full rounded-full bg-gradient-cta" style={{ width: `${Math.min(100, ((w.order_count ?? w.orders_count ?? 0) / Math.max(1, w.capacity || 1)) * 100)}%` }} /></div>
                <div className="flex gap-2">
                  <button onClick={() => setEditWindow(w)} className="flex-1 py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary transition">
                    <Pencil className="w-3 h-3 inline mr-1" />Edit
                  </button>
                  <button onClick={() => handleWindow(w.id, w.status === 'open' ? 'close' : 'reopen')} disabled={busy === w.id}
                    className={`flex-1 py-2 rounded-full text-xs font-bold disabled:opacity-50 ${w.status === 'open' ? 'tone-error border border-destructive/30' : 'tone-success border border-success/30'}`}>
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
                <div><div className="font-bold text-sm text-foreground">{b.zone || msg('FE_BATCH_LABEL', 'Delivery batch')}</div>{b.delivery_date && <time dateTime={b.delivery_date} className="block text-xs font-semibold text-foreground">{new Date(`${b.delivery_date}T12:00:00+01:00`).toLocaleDateString('en-NG', { timeZone: 'Africa/Lagos', day: 'numeric', month: 'short', year: 'numeric' })}</time>}<div className="text-xs text-muted-foreground font-mono">#{b.id.toUpperCase()}</div></div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full capitalize ${b.status === 'in_progress' ? 'tone-info' : b.status === 'assigned' ? 'tone-warn' : b.status === 'completed' ? 'tone-success' : 'bg-secondary text-muted-foreground'}`}>{b.status.replace(/_/g, ' ')}</span>
              </div>
              <div className="flex items-center justify-between text-xs"><span className="text-muted-foreground">Rider: {b.profiles?.full_name || b.rider_name || <span className="text-destructive">Unassigned</span>}</span><span className="font-bold text-foreground">{b.order_count ?? 0} orders</span></div>
              {b.status === 'open' && !b.rider_id && <p className="mt-2 text-xs text-muted-foreground">{msg('FE_BATCH_STAGED_SUMMARY', 'Ready orders grouped by gate and delivery window. Assign a rider to send this batch.')}</p>}
              {b.status !== 'completed' && b.status !== 'cancelled' && (
                <div className="flex gap-2 mt-2">
                  <button onClick={() => setManageBatch(b)} disabled={batchBusy === b.id} className="flex-1 py-1.5 rounded-full bg-secondary text-xs font-bold disabled:opacity-50">{!b.rider_id ? msg('FE_BATCH_ASSIGN_RIDER', 'Assign rider') : msg('FE_BATCH_MANAGE_ACTION', 'Manage / split')}</button>
                  {b.status !== 'open' && <button onClick={() => completeBatch(b.id)} disabled={batchBusy === b.id} className="flex-1 py-1.5 rounded-full bg-success text-white text-xs font-bold disabled:opacity-50">{batchBusy === b.id ? '...' : 'Mark Completed'}</button>}
                  <button onClick={() => cancelBatch(b.id)} disabled={batchBusy === b.id} className="px-3 py-1.5 rounded-full tone-error border border-destructive/30 text-xs font-bold disabled:opacity-50">Cancel</button>
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
              <h3 className="font-bold text-sm text-foreground flex items-center gap-1.5"><MapPin className="w-4 h-4 text-info" /> Off-Campus Gates</h3>
              <button onClick={() => setZoneModal({ type: 'gate' })} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-3 h-3" /> Add</button>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {gates.map((g) => {
                const isActive = g.is_active !== false;
                return (
                <div key={g.id} className={`rounded-xl bg-card border p-3 shadow-card ${isActive ? 'border-border' : 'border-border opacity-75'}`}>
                  <div className="flex items-center gap-2">
                    <MapPin className={`w-4 h-4 shrink-0 ${isActive ? 'text-info' : 'text-muted-foreground'}`} />
                    <div className="flex-1 min-w-0"><div className="font-bold text-xs text-foreground truncate">{g.name}</div><div className="text-[11px] text-muted-foreground">Base fee {formatNaira(g.base_fee)}</div></div>
                    {isActive ? <Pill tone="green">Active</Pill> : <Pill tone="red">Deactivated</Pill>}
                    <button onClick={() => setZoneModal({ type: 'gate', item: g })} className="p-1.5 rounded-lg hover:bg-secondary"><Pencil className="w-3.5 h-3.5 text-muted-foreground" /></button>
                  </div>
                  {!isActive && (
                    <button onClick={() => restoreGate(g.id)} className="mt-2 w-full px-3 py-1.5 rounded-full tone-success border border-success/30 text-[11px] font-bold">Restore gate</button>
                  )}
                </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {tab === 'area' && <AdminDeliveryArea />}
      {tab === 'riders' && <AdminRiders />}

      {tab === 'carts' && (
        <div className="space-y-2">
          <div className="rounded-xl tone-warn border border-warn/40 p-3 text-xs text-warn"><ShoppingCart className="w-4 h-4 inline mr-1" /> Carts inactive for 60+ minutes. Send a recovery nudge to bring them back.</div>
          {carts.map((c) => (
            <div key={c.id} className="rounded-2xl bg-card border border-border shadow-card p-3 flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${c.nudged ? 'tone-warn' : 'bg-primary/10'}`}><ShoppingCart className={`w-5 h-5 ${c.nudged ? 'text-warn' : 'text-primary'}`} /></div>
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{c.profiles?.full_name || c.user_name || 'User'}</div><div className="text-xs text-muted-foreground">{c.item_count ?? (Array.isArray(c.items) ? c.items.length : 0)} items · {formatNaira(c.total_value ?? c.subtotal ?? c.total ?? 0)} · last activity {timeAgo(c.last_active_at || c.last_activity || c.updated_at)}</div></div>
              {(c.recovery_attempts ?? 0) > 0 ? <span className="text-[10px] font-bold tone-warn px-2 py-1 rounded-full">Nudged</span>
                : <button onClick={() => handleNudge(c.id)} disabled={busy === c.id} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Send className="w-3 h-3" />Nudge</button>}
            </div>
          ))}
        </div>
      )}

      {showCreateWindow && <CreateWindowModal onClose={() => setShowCreateWindow(false)} onSaved={load} />}
      {editWindow && <CreateWindowModal window={editWindow} onClose={() => setEditWindow(null)} onSaved={load} />}
      {manageBatch && <AdminManageBatchModal batch={manageBatch} onClose={() => setManageBatch(null)} onSaved={load} />}
      {batchModal && <CreateBatchModal windows={windows} onClose={() => setBatchModal(false)} onSaved={load} />}
      {zoneModal && <ZoneModal type={zoneModal.type} item={zoneModal.item} onClose={() => setZoneModal(null)} onSave={saveZone} onDelete={deleteZone} />}
    </div>
  );
}

function CreateWindowModal({
  window: existing,
  onClose,
  onSaved,
}: {
  // TODO(ts): the delivery-window row is untyped; the modal mirrors it into
  // form fields with `existing?.x || ''` fallbacks.
   
  window?: Record<string, any> | null;
  onClose?: () => void;
  onSaved?: () => void | Promise<void>;
}) {
  const editing = !!existing;
  // Pre-fill from the existing window when editing. The backend stores starts_at/ends_at
  // as ISO instants; datetime-local inputs need the local-time slice (first 16 chars).
  const toLocal = (iso) => iso ? new Date(iso).toISOString().slice(0, 16) : '';
  const [form, setForm] = useState(existing
    ? { label: existing.label || '', starts_at: toLocal(existing.starts_at), ends_at: toLocal(existing.ends_at), capacity: existing.capacity ?? 50 }
    : { label: '', starts_at: '', ends_at: '', capacity: 50 });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!form.ends_at) { toast({ title: msg('FE_ADMIN_DELIVERY_END_TIME_REQUIRED', 'End time required'), variant: 'destructive' }); return; }
    if (form.starts_at && form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)) { toast({ title: msg('FE_ADMIN_DELIVERY_END_TIME_MUST_BE_AFTER_THE_START_TIME', 'End time must be after the start time'), variant: 'destructive' }); return; }
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
        toast({ title: msg('FE_ADMIN_DELIVERY_WINDOW_UPDATED', '✅ Window updated') });
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
        <Field label={msg('FE_CAPACITY_DELIVERY', 'Delivery planning target')}><TextInput type="number" value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} /></Field>
        <button onClick={submit} disabled={submitting || !form.label || !form.starts_at || !form.ends_at} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? (editing ? 'Saving...' : 'Creating...') : (editing ? 'Save Changes' : 'Create Window')}</button>
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
          {item && <button onClick={() => onDelete(type, item.id)} className="px-4 py-3 rounded-full tone-error border border-destructive/30 font-bold"><Trash2 className="w-4 h-4" /></button>}
        </div>
      </div>
    </Modal>
  );
}
