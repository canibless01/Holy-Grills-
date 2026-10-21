import { useEffect, useRef, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { Field, Modal, TextInput } from './AdminShared';
import LoadingSpinner from '@/components/LoadingSpinner';

/** Reassign a whole waiting batch, or move a selected waiting subset to another rider. */
export default function AdminManageBatchModal({ batch, onClose, onSaved }) {
  const [orders, setOrders] = useState<any[] | null>(null);
  const [riders, setRiders] = useState<any[]>([]);
  const [riderId, setRiderId] = useState(batch.rider_id || '');
  const [zone, setZone] = useState(batch.zone || '');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([liveApi.admin.getDeliveryBatch(batch.id), liveApi.admin.getUsers({ role: 'rider', campus_id: batch.campus_id })])
      .then(([detail, people]) => {
        if (!active) return;
        setOrders(detail?.orders || []);
        setRiders((people || []).filter(person => person.is_active !== false && person.campus_id === batch.campus_id));
      })
      .catch(failure => { if (active) { setError(failure.message); setOrders([]); } });
    return () => { active = false; };
  }, [batch.id, batch.campus_id]);
  const canReassign = ['open', 'assigned'].includes(batch.status) && !!orders?.length
    && orders.every(order => ['ready', 'assigned'].includes(order.status));
  const canSplit = selected.length > 0 && selected.length < (orders?.length || 0);
  const save = async (split: boolean) => {
    if (busy || !riderId || (split ? !canSplit : !canReassign)) return;
    setBusy(true); setError('');
    try {
      if (split) {
        const body = { rider_id: riderId, zone, order_ids: [...selected].sort() };
        const fingerprint = JSON.stringify(body);
        if (intent.current?.fingerprint !== fingerprint) intent.current = { fingerprint, key: crypto.randomUUID() };
        await liveApi.admin.splitDeliveryBatch(batch.id, { ...body, idempotency_key: intent.current.key });
      } else {
        await liveApi.admin.updateDeliveryBatch(batch.id, { rider_id: riderId, zone });
      }
      toast({ title: split ? msg('FE_BATCH_SPLIT_SAVED', 'Selected orders moved to a new batch') : msg('FE_BATCH_REASSIGN_SAVED', 'Batch updated') });
      onClose();
      // A refresh failure must not invite repeating a committed split.
      try { await onSaved?.(); } catch { /* Closing preserves the saved outcome. */ }
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  return <Modal open onClose={() => { if (!busy) onClose(); }} title={msg('FE_BATCH_MANAGE_TITLE', 'Manage delivery batch')}>
    {orders === null ? <LoadingSpinner /> : <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{msg('FE_BATCH_MANAGE_HELP', 'Reassign a waiting batch, or select some waiting orders to give another rider a new batch. Orders already on the road stay with their current rider.')}</p>
      <Field label={msg('FE_BATCH_RIDER', 'Rider')}>
        <select value={riderId} onChange={event => setRiderId(event.target.value)} disabled={busy} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
          <option value="">{msg('FE_BATCH_SELECT_RIDER', 'Select rider…')}</option>
          {riders.map(rider => <option key={rider.id} value={rider.id}>{rider.full_name}</option>)}
        </select>
      </Field>
      <Field label={msg('FE_BATCH_ZONE', 'Zone')}><TextInput value={zone} onChange={event => setZone(event.target.value)} disabled={busy} /></Field>
      <div className="max-h-64 overflow-y-auto rounded-xl border border-border">
        {orders.map(order => <label key={order.id} className="flex items-center gap-2 p-3 border-b border-border last:border-0 text-xs">
          <input type="checkbox" disabled={busy || order.status !== 'assigned'} checked={selected.includes(order.id)}
            onChange={event => setSelected(current => event.target.checked ? [...current, order.id] : current.filter(id => id !== order.id))} />
          <span className="min-w-0 flex-1"><span className="font-mono font-semibold">#{order.id.slice(0, 8).toUpperCase()}</span><span className="block text-muted-foreground">{(order.order_items || []).map(item => `${item.quantity}× ${item.name_snapshot}`).join(', ')}</span></span>
          <span className="capitalize text-muted-foreground">{order.status.replaceAll('_', ' ')}</span>
        </label>)}
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button type="button" disabled={busy || !riderId || !canReassign} onClick={() => save(false)} className="flex-1 rounded-full bg-secondary py-2.5 text-xs font-bold disabled:opacity-50">{msg('FE_BATCH_REASSIGN_ACTION', 'Update whole batch')}</button>
        <button type="button" disabled={busy || !riderId || !canSplit} onClick={() => save(true)} className="flex-1 rounded-full bg-gradient-cta text-white py-2.5 text-xs font-bold disabled:opacity-50">{msg('FE_BATCH_SPLIT_ACTION', 'Split selected orders')}</button>
      </div>
    </div>}
  </Modal>;
}
