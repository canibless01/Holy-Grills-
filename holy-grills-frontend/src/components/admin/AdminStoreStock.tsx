import { useEffect, useRef, useState } from 'react';
import { ArrowRightLeft, ArrowDownLeft, ArrowUpRight, Boxes, ChevronDown, MapPin, Package, Settings2 } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { toast } from '@/components/ui/use-toast';
import { Card, Modal } from './ui/AdminKit';

const actionLabel = (action: string) => action === 'purchase' ? msg('FE_STOCK_PURCHASE', 'Purchase') : action === 'usage' ? msg('FE_STOCK_USAGE', 'Usage') : action === 'waste' ? msg('FE_STOCK_WASTE', 'Waste') : msg('FE_STOCK_CORRECTION', 'Correction');

const numberFormat = new Intl.NumberFormat('en-NG', { maximumFractionDigits: 6 });
const quantityLabel = (value: unknown) => numberFormat.format(Number(value || 0));

const control = 'mt-1 w-full min-h-11 rounded-xl border border-border bg-background p-3 text-sm';
const button = 'min-h-11 rounded-full bg-primary px-5 text-sm font-bold text-white disabled:opacity-50';

export default function AdminStoreStock({ campusId, storeId = '' }) {
  const { user } = useHolyGrill();
  const kitchen = user?.role === 'kitchen';
  const [stores, setStores] = useState<any[]>([]);
  const [catalogError, setCatalogError] = useState('');
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [store, setStore] = useState(storeId);
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [movement, setMovement] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [history, setHistory] = useState<any>(null);
  const [showHistory, setShowHistory] = useState(false);
  const lock = useRef(false);
  const lastNotice = useRef<ReturnType<typeof toast> | null>(null);
  const generation = useRef(0);
  const intent = useCmsCreateIntent();
  useEffect(() => {
    let active = true;
    setCatalogError('');
    apiClient.get(kitchen ? '/admin/work-stores' : '/admin/stores', { campus_id: campusId }).then(data => { if (active) { setStores(data.stores || []); if (kitchen) setStore(current => current || data.stores?.[0]?.id || ''); } })
      .catch(failure => { if (active) setCatalogError(failure.message); });
    return () => { active = false; };
  }, [campusId, kitchen, catalogRetry]);
  useEffect(() => {
    const version = ++generation.current;
    if (kitchen && !store) { setLoading(false); setItems([]); return; }
    setLoading(true); setError(''); setHistory(null);
    apiClient.get('/admin/store-stock', { campus_id: campusId, ...(store ? { store_id: store } : {}) })
      .then(data => { if (generation.current === version) setItems(data.items || []); })
      .catch(failure => { if (generation.current === version) { setItems([]); setError(failure.message); } })
      .finally(() => { if (generation.current === version) setLoading(false); });
    return () => { generation.current++; };
  }, [campusId, store, revision, kitchen]);
  useEffect(() => {
    if (!showHistory || kitchen && !store) return;
    let active = true; setHistory(null);
    apiClient.get('/admin/store-stock', { campus_id: campusId, action: 'history', ...(store ? { store_id: store } : {}) })
      .then(data => { if (active) setHistory(data); }).catch(failure => { if (active) setHistory({ error: failure.message }); });
    return () => { active = false; };
  }, [campusId, store, revision, showHistory, kitchen]);
  const location = (id) => id ? stores.find(row => row.id === id)?.name || msg('FE_SUPPLY_UNKNOWN_STORE', 'Store unavailable') : msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen');
  const classify = async (item) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      await apiClient.post('/admin/store-stock', { campus_id: campusId, action: 'classify', item_id: item.id, distributable: !item.store_distributable });
      setRevision(value => value + 1);
    } catch (failure) { setError(failure.message); }
    finally { lock.current = false; setBusy(false); }
  };
  const save = async (event) => {
    event.preventDefault();
    if (lock.current || !movement) return;
    const quantity = Number(movement.quantity);
    if (!Number.isFinite(quantity) || quantity === 0 || (movement.action !== 'correction' && quantity < 0) || !movement.notes.trim()) {
      setFormError(msg('STORE_STOCK_INVALID', 'Enter a valid quantity and a reason for the stock movement.')); return;
    }
    lock.current = true; setBusy(true); setFormError('');
    try {
      await apiClient.post('/admin/store-stock', intent.body({ campus_id: campusId, store_id: store || null,
        action: movement.action, item_id: movement.item.id, quantity, notes: movement.notes.trim(),
        ...(movement.action === 'transfer' ? { destination_store_id: movement.destination || null } : {}) }));
      intent.clear(); setMovement(null); setRevision(value => value + 1);
      lastNotice.current?.dismiss();
      lastNotice.current = toast({ title: msg('FE_STORE_STOCK_SAVED', 'Stock movement recorded') });
    } catch (failure) { setFormError(failure.message); }
    finally { lock.current = false; setBusy(false); }
  };
  const open = (item, action) => { setFormError(''); setMovement({ item, action, quantity: '', notes: '', destination: store ? '' : stores.find(row => row.is_active)?.id || '' }); };
  return <div className="space-y-5">
    <header className="px-1 pt-1">
      <p className="text-[10px] font-extrabold tracking-[0.14em] text-primary">{msg('FE_SUPPLY_DESK_EYEBROW', 'CENTRAL KITCHEN · STORE OPERATIONS')}</p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2"><h2 className="font-heading text-3xl font-extrabold tracking-tight">{msg('FE_SUPPLY_DESK', 'Supply desk')}</h2><span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-accent" />{msg('FE_SUPPLY_TRACKING_TAG', 'Manual stock ledger')}</span></div>
      <p className="mt-2 max-w-lg text-xs leading-relaxed text-muted-foreground">{msg('FE_SUPPLY_DESK_INTRO', 'Receive centrally. Send to stores. Keep every movement accounted for.')}</p>
    </header>
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/20 text-brand-brown"><MapPin className="h-5 w-5" /></div>
      <label className="min-w-0 flex-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{msg('FE_STORE_STOCK_LOCATION', 'Stock location')}
        <select aria-label={msg('FE_STORE_STOCK_LOCATION', 'Stock location')} className="mt-1 block min-h-8 w-full truncate bg-transparent pr-6 text-base font-extrabold normal-case tracking-normal text-foreground outline-offset-4" disabled={busy} value={store} onChange={event => setStore(event.target.value)}>{!kitchen && <option value="">{msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')}</option>}{stores.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select>
      </label>
    </div>
    <details className="group border-b border-border/70 px-1 py-2.5 text-xs"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold"><span>{msg('FE_SUPPLY_TRACKING_HELP', 'How quantities are tracked')}</span><ChevronDown className="h-4 w-4 shrink-0 transition group-open:rotate-180" /></summary><div className="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground"><p>{msg('FE_STORE_STOCK_HELP', 'Ingredients stay central. Allocate packaging, utensils or prepared items to stores and record their usage. Purchases are received through Ingredient Stock.')}</p><p>{msg('FE_STORE_STOCK_MANUAL', 'Allocations track physical quantities. Orders do not automatically deduct ingredients or supplies; record usage after preparation or service.')}</p></div></details>
    {(error || catalogError) && <Card className="space-y-3 border-destructive/30 p-4"><p role="alert" className="text-sm text-destructive">{error || catalogError}</p><button className={button} onClick={() => { setRevision(value => value + 1); setCatalogRetry(value => value + 1); }}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></Card>}
    {loading ? <div role="status" className="animate-pulse space-y-3"><div className="h-52 rounded-3xl bg-secondary/60" /><span className="sr-only">{msg('FE_LOOKUP_LOADING', 'Loading…')}</span></div> : error || catalogError ? null : !items.length ? <div className="flex flex-col items-center gap-3 rounded-3xl border border-dashed border-border py-12 text-center"><Boxes className="h-8 w-8 text-muted-foreground/60" /><p className="max-w-xs px-4 text-sm text-muted-foreground">{msg('FE_STORE_STOCK_EMPTY', 'No ingredients or supplies have been added for this campus.')}</p></div> : <div className="grid gap-4 lg:grid-cols-2">{items.map(item => {
      const local = Number(store ? item.store_balance : item.central_balance);
      const total = Number(item.current_balance || 0);
      const allocated = Number(item.allocated_balance || 0);
      const share = total > 0 ? Math.max(0, Math.min(100, allocated / total * 100)) : 0;
      const low = local < Number(item.low_stock_threshold || 0);
      return <article aria-label={item.name} key={item.id} className="overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
        <div className="p-5">
          <div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-brand-brown"><Package className="h-5 w-5" /></div><div className="min-w-0"><h3 className="break-words font-heading text-base font-extrabold">{item.name}</h3><p className="mt-0.5 text-[11px] text-muted-foreground">{item.archived_at ? msg('FE_SUPPLY_ARCHIVED', 'Archived') : item.store_distributable ? msg('FE_SUPPLY_DISTRIBUTABLE', 'Store supply') : msg('FE_SUPPLY_CENTRAL_ONLY', 'Central ingredient')}</p></div></div>{low && !item.archived_at && <span className="shrink-0 rounded-full bg-destructive/10 px-2.5 py-1 text-[10px] font-bold text-destructive">{msg('FE_SUPPLY_LOW', 'Low stock')}</span>}</div>
          <div className="mt-5 flex items-end justify-between gap-3"><div><p className="text-[11px] font-semibold text-muted-foreground">{msg('FE_SUPPLY_AVAILABLE', 'Available here')}</p><p className="mt-1 font-heading text-4xl font-extrabold tracking-tight">{quantityLabel(local)}<span className="ml-2 text-sm font-semibold tracking-normal text-muted-foreground">{item.usage_unit}</span></p></div>{!kitchen && <div className="pb-1 text-right"><p className="text-[10px] text-muted-foreground">{msg('FE_STORE_STOCK_CAMPUS', 'Campus total')}</p><p className="mt-1 text-sm font-extrabold">{quantityLabel(total)}</p></div>}</div>
          {!kitchen && <div className="mt-4"><div aria-hidden="true" className="flex h-1.5 overflow-hidden rounded-full bg-secondary"><div className="bg-accent transition-[width]" style={{ width: `${100 - share}%` }} /><div className="bg-primary transition-[width]" style={{ width: `${share}%` }} /></div><div className="mt-2 flex flex-wrap justify-between gap-x-4 gap-y-1 text-[10px] text-muted-foreground"><span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-accent" />{msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')} <strong className="text-foreground">{quantityLabel(item.central_balance)}</strong></span><span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-primary" />{msg('FE_STORE_STOCK_ALLOCATED', 'At stores')} <strong className="text-foreground">{quantityLabel(allocated)}</strong></span></div></div>}
          {!kitchen && Number(item.central_balance) < 0 && <p role="alert" className="mt-3 text-xs text-destructive">{msg('FE_STORE_STOCK_DRIFT', 'Allocated stock exceeds the recorded campus balance. Reconcile the stock ledger before making further movements.')}</p>}
          {item.store_distributable && !item.archived_at && <div className="mt-5 space-y-2.5">{store && <button disabled={busy || local <= 0} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-gradient-cta px-5 text-sm font-extrabold text-white shadow-sm disabled:opacity-50" onClick={() => open(item, 'usage')}><ArrowUpRight className="h-4 w-4" />{actionLabel('usage')}</button>}{!kitchen && <button disabled={busy || !store && !stores.some(row => row.is_active)} className={`flex min-h-11 w-full items-center justify-center gap-2 rounded-full px-4 text-sm font-bold disabled:opacity-50 ${store ? 'border border-border bg-background' : 'bg-gradient-cta text-white shadow-sm'}`} onClick={() => open(item, 'transfer')}><ArrowRightLeft className="h-4 w-4" />{msg('FE_STORE_STOCK_TRANSFER', 'Transfer stock')}</button>}{store && <div className="flex items-center justify-center gap-5">{(kitchen ? ['waste'] : ['waste', 'correction']).map(action => <button key={action} disabled={busy || action === 'waste' && local <= 0} className="min-h-9 text-xs font-semibold text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50" onClick={() => open(item, action)}>{actionLabel(action)}</button>)}</div>}</div>}
        </div>
        {!store && <details className="group border-t border-border/60 bg-secondary/20 px-5 py-3 text-xs"><summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-muted-foreground"><Settings2 className="h-3.5 w-3.5" />{msg('FE_SUPPLY_SETTINGS', 'Tracking settings')}<ChevronDown className="ml-auto h-3.5 w-3.5 transition group-open:rotate-180" /></summary><label className="mt-3 flex items-center gap-2 leading-relaxed"><input type="checkbox" disabled={busy || !!item.archived_at} checked={item.store_distributable} onChange={() => classify(item)} />{msg('FE_STORE_STOCK_DISTRIBUTABLE', 'Allocate this item to stores')}</label></details>}
      </article>;
    })}</div>}
    <section className="rounded-2xl border border-border bg-card"><button className="flex min-h-14 w-full items-center justify-between gap-3 px-5 text-sm font-extrabold" onClick={() => setShowHistory(value => !value)} aria-expanded={showHistory}><span>{msg('FE_STORE_STOCK_RECENT', 'Recent stock movements')}</span><ChevronDown className={`h-4 w-4 text-muted-foreground transition ${showHistory ? 'rotate-180' : ''}`} /></button>
      {showHistory && <div className="space-y-3 border-t border-border px-5 py-4">{!history ? <p role="status">{msg('FE_LOOKUP_LOADING', 'Loading…')}</p> : history.error ? <p role="alert">{history.error}</p> : !history.entries.length ? <p className="py-4 text-center text-sm text-muted-foreground">{msg('FE_SUPPLY_HISTORY_EMPTY', 'No movements recorded for this location yet.')}</p> : history.entries.map(row => <div className="flex items-start gap-3 border-b border-border/60 pb-3 text-sm last:border-0 last:pb-0" key={row.id}><span className={`mt-0.5 rounded-xl p-2 ${Number(row.quantity_in_usage_units) > 0 ? 'bg-success/10 text-success' : 'bg-primary/10 text-primary'}`}>{Number(row.quantity_in_usage_units) > 0 ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap justify-between gap-2"><strong>{row.item_name}</strong><strong className="tabular-nums">{Number(row.quantity_in_usage_units) > 0 ? '+' : ''}{quantityLabel(row.quantity_in_usage_units)} <span className="text-xs font-normal text-muted-foreground">{row.unit_name}</span></strong></div><p className="mt-1 text-[11px] text-muted-foreground">{row.store_transfer_id ? `${location(row.store_movement?.store_id)} → ${location(row.store_movement?.destination_store_id)}` : `${row.store_name || msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')} · ${actionLabel(row.type)}`}</p><p className="mt-1 break-words text-xs">{row.notes}</p><time className="mt-1 block text-[10px] text-muted-foreground" dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })}</time></div></div>)}</div>}
    </section>
    {movement && <Modal open title={movement.item.name} onClose={() => { if (!busy) setMovement(null); }}><form className="space-y-4" onSubmit={save}><p className="text-sm font-bold">{location(store)} · {movement.action === 'transfer' ? msg('FE_STORE_STOCK_TRANSFER', 'Transfer stock') : actionLabel(movement.action)}</p>
      {movement.action === 'transfer' && <label className="block text-sm">{msg('FE_STORE_STOCK_TO', 'Destination')}<select aria-label={msg('FE_STORE_STOCK_TO', 'Destination')} required={!store} className={control} value={movement.destination} onChange={event => setMovement({ ...movement, destination: event.target.value })}>{store && <option value="">{msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')}</option>}{stores.filter(row => row.id !== store && row.is_active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
      <label className="block text-sm">{movement.action === 'correction' ? msg('FE_STORE_STOCK_CHANGE', 'Signed change in usage units (positive adds stock)') : msg('FE_STORE_STOCK_QUANTITY', 'Quantity in usage units')}<input required type="number" step="any" min={movement.action === 'correction' ? undefined : '0.000001'} className={control} value={movement.quantity} onChange={event => setMovement({ ...movement, quantity: event.target.value })} /></label>
      <label className="block text-sm">{msg('FE_STORE_STOCK_REASON', 'Reason / dispatch note')}<textarea required maxLength={1000} className={control} value={movement.notes} onChange={event => setMovement({ ...movement, notes: event.target.value })} /></label>{formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}<button disabled={busy} className={`${button} w-full`} type="submit">{msg('FE_STORE_STOCK_SAVE', 'Record movement')}</button></form></Modal>}
  </div>;
}
