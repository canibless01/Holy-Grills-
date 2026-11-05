import { useState, useEffect, useRef } from 'react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Modal, Field, TextInput } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import { CheckSquare, Square, Truck } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';

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
 * Only paid, ready, unbatched orders are eligible. A preset still has to meet
 * those same rules; scheduled orders become assignable after preparation.
 */
export default function CreateBatchModal({ windows = [], presetOrderIds = [], onClose, onSaved }: {
  windows?: Array<{ id?: string | number; label?: string; campus_id?: string; starts_at?: string; delivery_date?: string }>;
  presetOrderIds?: string[];
  onClose?: () => void;
  onSaved?: () => void | Promise<void>;
}) {
  const [windowId, setWindowId] = useState('');
  const { campuses, adminCampusId } = useCampus();
  const [riderId, setRiderId] = useState('');
  const [zone, setZone] = useState('');
  const [riders, setRiders] = useState([]);
  const [orders, setOrders] = useState(null); // null = still loading
  const [selected, setSelected] = useState(new Set(presetOrderIds));
  const [submitting, setSubmitting] = useState(false);
  const preset = presetOrderIds.length > 0;
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);
  const selectedWindow = windows.find(window => String(window.id) === String(windowId));
  const readyOrders = (orders || []).filter(order => order.status === 'ready' && !order.batch_id && ['paid', 'partially_refunded'].includes(order.payment_status)
    && (!adminCampusId || order.campus_id === adminCampusId));
  const availableWindows = windows.filter(window => (!adminCampusId || window.campus_id === adminCampusId)
    && readyOrders.some(order => (!order.delivery_window_id || String(order.delivery_window_id) === String(window.id)) && (!window.campus_id || order.campus_id === window.campus_id)));
  const windowLabel = window => {
    const campusName = campuses.find(campus => campus.id === window.campus_id)?.name || 'Campus';
    const stamp = window.delivery_date || window.starts_at;
    const date = stamp && Number.isFinite(new Date(stamp).getTime()) ? new Date(stamp).toLocaleDateString('en-NG', { timeZone: 'Africa/Lagos', day: 'numeric', month: 'short' }) : '';
    return [window.label || 'Delivery window', date, campusName, `#${String(window.id).slice(0, 6).toUpperCase()}`].filter(Boolean).join(' · ');
  };
  const eligibleOrders = (orders || []).filter(order => order.status === 'ready' && !order.batch_id
    && ['paid', 'partially_refunded'].includes(order.payment_status)
    && (!selectedWindow?.campus_id || order.campus_id === selectedWindow.campus_id)
    && (!order.delivery_window_id || String(order.delivery_window_id) === String(windowId)));
  const eligibleRiders = riders.filter(rider => rider.is_active !== false
    && (!selectedWindow?.campus_id || rider.campus_id === selectedWindow.campus_id));
  const eligibleIdsKey = eligibleOrders.map(order => order.id).sort().join(',');
  useEffect(() => {
    if (orders === null || !windowId) return;
    const allowed = new Set(eligibleIdsKey.split(','));
    setSelected(current => new Set([...current].filter(id => allowed.has(id))));
    setRiderId(current => eligibleRiders.some(rider => rider.id === current) ? current : '');
  }, [eligibleIdsKey, windowId, riders]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    (async () => {
      try { const r = await mockApi.admin.getUsers({ role: 'rider' }); setRiders(r || []); } catch { setRiders([]); }
      try { setOrders(await mockApi.admin.getAdminOrders({ status: 'ready' }) || []); }
      catch { setOrders([]); }
    })();
  }, []);

  const toggle = (id) => { const n = new Set(selected); if (n.has(id)) n.delete(id); else n.add(id); setSelected(n); };

  const submit = async () => {
    if (!windowId || !riderId) { toast({ title: msg('FE_ADMIN_DELIVERY_MISSING_FIELDS', 'Missing fields'), description: msg('FE_BATCH_WINDOW_RIDER_REQUIRED', 'Choose a delivery window and rider.'), variant: 'destructive' }); return; }
    if (selected.size === 0) { toast({ title: msg('FE_BATCH_NO_ORDERS', 'No order selected'), description: msg('FE_BATCH_PICK_ORDERS', 'Pick at least one paid, ready order to assign.'), variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      const body = { window_id: windowId, rider_id: riderId, zone, order_ids: [...selected].sort() };
      const fingerprint = JSON.stringify(body);
      if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
      await mockApi.admin.createDeliveryBatch({ ...body, idempotency_key: intent.current.key });
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
        {orders !== null && preset && !presetOrderIds.some(id => eligibleOrders.some(order => order.id === id)) && <p role="alert" className="text-xs text-warn">{msg('FE_BATCH_PRESET_CHANGED', 'This order is not currently ready for assignment in this window. Refresh its status or choose another eligible order.')}</p>}
        <Field label="Delivery Window">
          {orders === null ? <p className="text-sm text-muted-foreground">Loading ready orders and their delivery windows…</p> : availableWindows.length === 0 ? (
            <div className="rounded-xl tone-warn border border-warn/40 p-3 text-xs text-warn mt-1">
              No delivery window has paid, ready, unassigned orders in this campus. Prepare the orders in Kitchen first, then assign a rider. Configure missing delivery times in <b>Delivery → Delivery times</b>.
            </div>
          ) : (
            <select value={windowId} onChange={(e) => setWindowId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
              <option value="">Select window…</option>
              {availableWindows.map((w) => <option key={w.id} value={w.id}>{windowLabel(w)}</option>)}
            </select>
          )}
        </Field>
        <Field label="Rider">
          <select value={riderId} onChange={(e) => setRiderId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
            <option value="">Select rider…</option>
            {eligibleRiders.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}
          </select>
        </Field>
        <Field label={msg('FE_BATCH_ZONE_OPTIONAL', 'Zone (optional)')}><TextInput value={zone} onChange={(e) => setZone(e.target.value)} placeholder="e.g. North Gate" /></Field>
        <Field label={preset ? 'Order to assign (add more if they ride together)' : 'Assign Orders'}>
          <div className="max-h-48 overflow-y-auto rounded-xl border border-border mt-1">
            {orders === null ? (
              <div className="p-3"><LoadingSpinner label="Loading orders…" /></div>
            ) : eligibleOrders.length === 0 ? (
              <div className="p-3 text-xs text-muted-foreground">{msg('FE_BATCH_NO_READY_ORDERS', 'No paid, ready, unassigned orders match this window.')}</div>
            ) : eligibleOrders.map((o) => {
              const isPreset = presetOrderIds.includes(o.id);
              return (
                <button key={o.id} type="button" onClick={() => toggle(o.id)} className={`w-full text-left p-2.5 flex items-center gap-2 border-b border-border last:border-0 ${selected.has(o.id) ? 'bg-primary/10' : 'hover:bg-muted'}`}>
                  {selected.has(o.id) ? <CheckSquare className="w-3.5 h-3.5 text-primary shrink-0" /> : <Square className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
                  <span className="text-xs font-mono text-muted-foreground shrink-0">#{o.id.slice(0, 6).toUpperCase()}</span>
                  <span className="text-xs text-muted-foreground truncate flex-1">{(o.order_items || []).map((it) => `${it.quantity}× ${it.name_snapshot || it.name}`).join(', ')}</span>
                  <span className="text-[10px] font-bold text-muted-foreground shrink-0">
                    {msg('FE_BATCH_READY', 'Ready')}{o.total_amount ? ` · ${formatNaira(o.total_amount)}` : ''}
                  </span>
                  {isPreset && <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-primary/15 text-primary shrink-0">this one</span>}
                </button>
              );
            })}
          </div>
        </Field>
        <button onClick={submit} disabled={submitting || !windowId || !riderId || selected.size === 0} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50 flex items-center justify-center gap-2">
          <Truck className="w-4 h-4" />
          {submitting ? 'Assigning…' : `Assign ${selected.size || ''} ${selected.size === 1 ? 'order' : 'orders'} to rider`}
        </button>
      </div>
    </Modal>
  );
}
