import DeliveryAddress from '@/components/DeliveryAddress';
import { useEffect, useState, useRef } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import OrderItemCustomizations from '@/components/OrderItemCustomizations';

export default function KitchenHandoff({ campusId = undefined }: { campusId?: string } = {}) {
  const scope = useRef(campusId); scope.current = campusId;
  const guard = useRef(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState({});
  const [chosen, setChosen] = useState<string[]>([]);
  const [bulkRider, setBulkRider] = useState('');
  const [assignmentErrors, setAssignmentErrors] = useState<string[]>([]);
  const [assignmentResult, setAssignmentResult] = useState('');
  const [busy, setBusy] = useState(null);
  const load = async () => {
    const requestedCampus = campusId;
    try { const value = await liveApi.kitchen.getHandoff(campusId); if (scope.current === requestedCampus) { setData(value); setError(false); } }
    catch { if (scope.current === requestedCampus) setError(true); }
  };
  useEffect(() => {
    let active = true; setChosen([]); setBulkRider(''); setData(null); setAssignmentResult(''); setAssignmentErrors([]);
    const refresh = async () => {
      if (document.visibilityState === 'hidden') return;
      try { const value = await liveApi.kitchen.getHandoff(campusId); if (active) { setData(value); setError(false); } }
      catch { if (active) setError(true); }
    };
    refresh(); const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [campusId]);
  const assign = async (batch) => {
    if (guard.current) return;
    guard.current = true;
    setBusy(batch.id);
    try {
      await liveApi.kitchen.assignHandoffRider(batch.id, { rider_id: selected[batch.id] || batch.rider_id }, campusId);
      await load();
      toast({ title: msg('FE_KITCHEN_RIDER_SAVED', 'Rider assignment saved') });
    } catch (exception) {
      toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: exception.message, variant: 'destructive' });
    } finally { guard.current = false; setBusy(null); }
  };
  const assignSelected = async () => {
    if (guard.current || !chosen.length || !bulkRider) return;
    guard.current = true; const requestedCampus = campusId;
    setBusy('bulk'); setAssignmentResult(''); setAssignmentErrors([]);
    const failed: string[] = []; const errors: string[] = []; let saved = 0;
    try {
      for (const id of chosen) {
        if (scope.current !== requestedCampus) return;
        try { await liveApi.kitchen.assignHandoffRider(id, { rider_id: bulkRider }, campusId); saved++; }
        catch (exception) { failed.push(id); errors.push(`${data.batches.find((batch) => batch.id === id)?.zone || id}: ${exception.message || 'Assignment refused'}`); }
      }
      if (scope.current !== requestedCampus) return;
      setChosen(failed); setAssignmentErrors(errors); await load();
      setAssignmentResult(`${saved} ${saved === 1 ? 'batch' : 'batches'} assigned${failed.length ? ` · ${failed.length} could not be assigned. Review and retry those selected batches.` : '.'}`);
    } finally { guard.current = false; setBusy(null); }
  };
  return <div className="space-y-3">
    <p className="rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">{msg('FE_KITCHEN_HANDOFF_HELP', 'Assign a rider to a ready batch, check its items, then hand it over. The assigned rider confirms pickup in their rider screen; no admin confirmation is needed.')}</p>
    {!!data?.batches?.length && <div className="rounded-xl border border-border bg-card p-3 space-y-2">
      <label className="flex gap-2 text-sm"><input type="checkbox" disabled={!!busy} checked={chosen.length > 0 && data.batches.every((batch) => chosen.includes(batch.id))} onChange={(event) => setChosen(event.target.checked ? data.batches.map((batch) => batch.id) : [])} /> Select all batches</label>
      <label className="block text-sm">Rider for selected batches<select aria-label="Rider for selected batches" value={bulkRider} onChange={(event) => setBulkRider(event.target.value)} disabled={!!busy} className="mt-1 w-full rounded-lg border border-border bg-background p-2"><option value="">Choose a rider</option>{(data.riders || []).map((rider) => <option key={rider.id} value={rider.id}>{rider.full_name}</option>)}</select></label>
      <button type="button" onClick={assignSelected} disabled={!!busy || !chosen.length || !bulkRider} className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-40">{busy === 'bulk' ? 'Assigning…' : `Assign ${chosen.length} selected ${chosen.length === 1 ? 'batch' : 'batches'}`}</button>
      <p className="text-xs text-muted-foreground">Each zone keeps its own batch. Successful assignments stay saved if another batch needs a retry.</p>
    </div>}
    {assignmentResult && <p role="status" className="rounded-xl border border-border p-3 text-sm">{assignmentResult}</p>}
    {assignmentErrors.length > 0 && <ul className="text-sm text-destructive">{assignmentErrors.map((error) => <li key={error}>{error}</li>)}</ul>}
    {error && <button onClick={load} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button>}
    {!data && !error && <p role="status">{msg('FE_LOOKUP_SEARCHING', 'Searching…')}</p>}
    {data?.batches?.length === 0 && <p className="py-8 text-center text-muted-foreground">{msg('FE_KITCHEN_HANDOFF_EMPTY', 'No ready batches awaiting handover.')}</p>}
    {(data?.batches || []).map(batch => <section key={batch.id} className="rounded-2xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between gap-2"><label className="flex items-center gap-2"><input type="checkbox" aria-label={`Select ${batch.zone || batch.id}`} disabled={!!busy} checked={chosen.includes(batch.id)} onChange={(event) => setChosen((current) => event.target.checked ? [...current, batch.id] : current.filter((id) => id !== batch.id))} /><strong>{batch.zone || msg('FE_BATCH_LABEL', 'Delivery batch')}</strong></label><span className="text-xs text-muted-foreground">{batch.delivery_date}</span></div>
      {batch.orders.map(order => <div key={order.id} className="border-b border-border pb-2 text-sm">
        <p className="font-semibold">{order.stop_label} · {order.customer_name || order.guest_name} · #{order.id.slice(0, 8).toUpperCase()}</p>
        <DeliveryAddress order={order} />
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
