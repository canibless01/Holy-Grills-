import { useState, useEffect } from 'react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Modal, Field, TextInput } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import { CheckSquare, Square, Truck } from 'lucide-react';

/**
 * CreateBatchModal — THE assignment flow: puts one or many orders on a rider
 * under a delivery window (POST createDeliveryBatch — the same endpoint the
 * Delivery → Batches tab has always used).
 *
 * Opened from two places:
 *   • AdminDelivery → Batches → "New Batch" (no preset — pick any ready orders)
 *   • AdminOrders → row "Assign" action (presetOrderIds preselects that order,
 *     so an admin standing on an order can assign it without hunting through
 *     the Delivery tab — the flow that used to be effectively undiscoverable).
 *
 * presetOrderIds also merges SCHEDULED/off-window orders into the pick list
 * (GET /orders/scheduled — an endpoint that already existed for the scheduled
 * list), so an order that arrived outside an open window can be assigned too;
 * the admin just picks (or creates) the window it should ride in.
 */
export default function CreateBatchModal({ windows = [], presetOrderIds = [], onClose, onSaved }: {
  windows?: Array<{ id?: string | number; label?: string }>;
  presetOrderIds?: string[];
  onClose?: () => void;
  onSaved?: () => void | Promise<void>;
}) {
  const [windowId, setWindowId] = useState(windows[0]?.id || '');
  const [riderId, setRiderId] = useState('');
  const [zone, setZone] = useState('');
  const [riders, setRiders] = useState([]);
  const [orders, setOrders] = useState(null); // null = still loading
  const [selected, setSelected] = useState(new Set(presetOrderIds));
  const [submitting, setSubmitting] = useState(false);
  const preset = presetOrderIds.length > 0;

  useEffect(() => {
    (async () => {
      try { const r = await mockApi.admin.getUsers({ role: 'rider' }); setRiders(r || []); } catch { setRiders([]); }
      // Ready orders + scheduled/off-window orders (the preset order may be one).
      const results = await Promise.allSettled([
        mockApi.admin.getAdminOrders({ status: 'ready' }),
        mockApi.orders.getScheduled(),
      ]);
      const ready = results[0].status === 'fulfilled' ? (results[0].value || []) : [];
      const scheduledRows = results[1].status === 'fulfilled' ? (results[1].value?.scheduled_orders || []) : [];
      const byId = new Map();
      [...ready, ...scheduledRows].forEach((o) => { if (o?.id && !byId.has(o.id)) byId.set(o.id, o); });
      setOrders(Array.from(byId.values()));
    })();
  }, []);

  const toggle = (id) => { const n = new Set(selected); if (n.has(id)) n.delete(id); else n.add(id); setSelected(n); };

  const submit = async () => {
    if (!windowId || !riderId || !zone) { toast({ title: msg('FE_ADMIN_DELIVERY_MISSING_FIELDS', 'Missing fields'), description: msg('FE_ADMIN_DELIVERY_WINDOW_RIDER_AND_ZONE_ARE_ALL_REQUIRED', 'Window, rider and zone are all required.'), variant: 'destructive' }); return; }
    if (selected.size === 0) { toast({ title: 'No order selected', description: 'Pick at least one order to assign.', variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      await mockApi.admin.createDeliveryBatch({ window_id: windowId, rider_id: riderId, zone, order_ids: [...selected] });
      toast({ title: msg('FE_ADMIN_DELIVERY_BATCH_CREATED', '✅ Batch created'), description: msg('FE_ADMIN_DELIVERY_COUNT_ORDER_S_ASSIGNED', '{count} order(s) assigned.', { count: selected.size }) });
      onSaved?.(); onClose?.();
    } catch (e) { toast({ title: msg('FE_ADMIN_DELIVERY_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={preset ? 'Assign Order to Rider' : 'Assign Delivery Batch'}>
      <div className="space-y-3">
        <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">
          {preset
            ? <>This creates a delivery batch for the selected order — the rider sees it the moment it's created. You can add more orders below.</>
            : <>A batch groups orders for one rider in one zone under a delivery window. Assigned orders move to <b>assigned</b> status.</>}
        </div>
        <Field label="Delivery Window">
          {windows.length === 0 ? (
            <div className="rounded-xl tone-warn border border-warn/40 p-3 text-xs text-warn mt-1">
              No delivery window exists yet. Create one first in <b>Delivery → Windows → New Window</b>, then assign the order — it only takes a few seconds.
            </div>
          ) : (
            <select value={windowId} onChange={(e) => setWindowId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
              <option value="">Select window…</option>
              {windows.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
            </select>
          )}
        </Field>
        <Field label="Rider">
          <select value={riderId} onChange={(e) => setRiderId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            <option value="">Select rider…</option>
            {riders.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}
          </select>
        </Field>
        <Field label="Zone"><TextInput value={zone} onChange={(e) => setZone(e.target.value)} placeholder="e.g. North Gate" /></Field>
        <Field label={preset ? 'Order to assign (add more if they ride together)' : 'Assign Orders'}>
          <div className="max-h-48 overflow-y-auto rounded-xl border border-border mt-1">
            {orders === null ? (
              <div className="p-3"><LoadingSpinner label="Loading orders…" /></div>
            ) : orders.length === 0 ? (
              <div className="p-3 text-xs text-muted-foreground">No ready or scheduled orders available to assign.</div>
            ) : orders.map((o) => {
              const isPreset = presetOrderIds.includes(o.id);
              return (
                <button key={o.id} type="button" onClick={() => toggle(o.id)} className={`w-full text-left p-2.5 flex items-center gap-2 border-b border-border last:border-0 ${selected.has(o.id) ? 'bg-primary/10' : 'hover:bg-muted'}`}>
                  {selected.has(o.id) ? <CheckSquare className="w-3.5 h-3.5 text-primary shrink-0" /> : <Square className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
                  <span className="text-xs font-mono text-muted-foreground shrink-0">#{o.id.slice(0, 6).toUpperCase()}</span>
                  <span className="text-xs text-muted-foreground truncate flex-1">{(o.order_items || []).map((it) => `${it.quantity}× ${it.name_snapshot || it.name}`).join(', ')}</span>
                  <span className="text-[10px] font-bold text-muted-foreground shrink-0">
                    {o.status === 'scheduled' || o.is_scheduled ? 'scheduled' : 'ready'}{o.total_amount ? ` · ${formatNaira(o.total_amount)}` : ''}
                  </span>
                  {isPreset && <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-primary/15 text-primary shrink-0">this one</span>}
                </button>
              );
            })}
          </div>
        </Field>
        <button onClick={submit} disabled={submitting || !windowId || !riderId || !zone || selected.size === 0} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50 flex items-center justify-center gap-2">
          <Truck className="w-4 h-4" />
          {submitting ? 'Assigning…' : `Assign ${selected.size || ''} ${selected.size === 1 ? 'order' : 'orders'} to rider`}
        </button>
      </div>
    </Modal>
  );
}
