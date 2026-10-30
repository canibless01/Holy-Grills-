import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import OrderItemCustomizations from '@/components/OrderItemCustomizations';

export default function KitchenHandoff({ campusId = undefined }: { campusId?: string } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState({});
  const [busy, setBusy] = useState(null);
  const load = async () => {
    try { setData(await liveApi.kitchen.getHandoff(campusId)); setError(false); }
    catch { setError(true); }
  };
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try { const value = await liveApi.kitchen.getHandoff(campusId); if (active) { setData(value); setError(false); } }
      catch { if (active) setError(true); }
    };
    refresh(); const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [campusId]);
  const assign = async (batch) => {
    if (busy) return;
    setBusy(batch.id);
    try {
      await liveApi.kitchen.assignHandoffRider(batch.id, { rider_id: selected[batch.id] || batch.rider_id }, campusId);
      await load();
      toast({ title: msg('FE_KITCHEN_RIDER_SAVED', 'Rider assignment saved') });
    } catch (exception) {
      toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: exception.message, variant: 'destructive' });
    } finally { setBusy(null); }
  };
  return <div className="space-y-3">
    <p className="rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">{msg('FE_KITCHEN_HANDOFF_HELP', 'Assign a rider to a ready batch, check its items, then hand it over. The assigned rider confirms pickup in their rider screen; no admin confirmation is needed.')}</p>
    {error && <button onClick={load} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button>}
    {!data && !error && <p role="status">{msg('FE_LOOKUP_SEARCHING', 'Searching…')}</p>}
    {data?.batches?.length === 0 && <p className="py-8 text-center text-muted-foreground">{msg('FE_KITCHEN_HANDOFF_EMPTY', 'No ready batches awaiting handover.')}</p>}
    {(data?.batches || []).map(batch => <section key={batch.id} className="rounded-2xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between gap-2"><strong>{batch.zone || msg('FE_BATCH_LABEL', 'Delivery batch')}</strong><span className="text-xs text-muted-foreground">{batch.delivery_date}</span></div>
      {batch.orders.map(order => <div key={order.id} className="border-b border-border pb-2 text-sm">
        <p className="font-semibold">{order.customer_name || order.guest_name} · #{order.id.slice(0, 8).toUpperCase()}</p>
        {(order.order_items || []).map((item, index) => <div key={index}>{item.quantity}× {item.name_snapshot}<OrderItemCustomizations item={item} /></div>)}
      </div>)}
      <label className="block text-xs font-bold">{msg('FE_KITCHEN_HANDOFF_RIDER', 'Rider')}<select aria-label={msg('FE_KITCHEN_HANDOFF_RIDER', 'Rider')} value={selected[batch.id] ?? batch.rider_id ?? ''} onChange={event => setSelected(current => ({ ...current, [batch.id]: event.target.value }))} className="mt-1 block w-full rounded-xl border border-border bg-background p-3 text-sm" disabled={!!busy}>
        <option value="">{msg('FE_KITCHEN_CHOOSE_RIDER', 'Choose a rider')}</option>
        {(data?.riders || []).map(rider => <option key={rider.id} value={rider.id}>{rider.full_name}</option>)}
      </select></label>
      <button onClick={() => assign(batch)} disabled={!!busy || !(selected[batch.id] || batch.rider_id) || (batch.status === 'assigned' && (!selected[batch.id] || selected[batch.id] === batch.rider_id))} className="w-full rounded-full bg-gradient-cta py-3 text-sm font-bold text-white disabled:opacity-40">{busy === batch.id ? msg('FE_ONBOARDING_SAVING', 'Saving…') : msg('FE_KITCHEN_SAVE_RIDER', 'Save rider')}</button>
      {batch.status === 'assigned' && <p className="text-xs text-muted-foreground">{msg('FE_KITCHEN_PICKUP_WAITING', 'Assigned. Waiting for the rider to confirm pickup.')}</p>}
    </section>)}
  </div>;
}
