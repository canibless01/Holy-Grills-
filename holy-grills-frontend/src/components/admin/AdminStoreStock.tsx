import { useEffect, useRef, useState } from 'react';
import { ArrowRightLeft, Boxes } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { toast } from '@/components/ui/use-toast';
import { Card, Modal } from './ui/AdminKit';

const actionLabel = (action: string) => action === 'purchase' ? msg('FE_STOCK_PURCHASE', 'Purchase') : action === 'usage' ? msg('FE_STOCK_USAGE', 'Usage') : action === 'waste' ? msg('FE_STOCK_WASTE', 'Waste') : msg('FE_STOCK_CORRECTION', 'Correction');

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
      .catch(failure => { if (generation.current === version) setError(failure.message); })
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
  const location = (id) => stores.find(row => row.id === id)?.name || msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen');
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
      toast({ title: msg('FE_STORE_STOCK_SAVED', 'Stock movement recorded') });
    } catch (failure) { setFormError(failure.message); }
    finally { lock.current = false; setBusy(false); }
  };
  const open = (item, action) => { setFormError(''); setMovement({ item, action, quantity: '', notes: '', destination: store ? '' : stores.find(row => row.is_active)?.id || '' }); };
  return <div className="space-y-4">
    <Card className="space-y-3 p-5"><h3 className="flex items-center gap-2 font-heading text-xl font-bold"><Boxes className="h-5 w-5 text-primary" />{msg('FE_STORE_STOCK_TITLE', 'Central kitchen & store supplies')}</h3><p className="text-sm text-muted-foreground">{msg('FE_STORE_STOCK_HELP', 'Ingredients stay central. Allocate packaging, utensils or prepared items to stores and record their usage. Purchases are received through Ingredient Stock.')}</p><p className="text-xs text-muted-foreground">{msg('FE_STORE_STOCK_MANUAL', 'Allocations track physical quantities. Orders do not automatically deduct ingredients or supplies; record usage after preparation or service.')}</p>
      <label className="block text-sm font-bold">{msg('FE_STORE_STOCK_LOCATION', 'Stock location')}<select aria-label={msg('FE_STORE_STOCK_LOCATION', 'Stock location')} className={control} disabled={busy} value={store} onChange={event => setStore(event.target.value)}>{!kitchen && <option value="">{msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')}</option>}{stores.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
    </Card>
    {(error || catalogError) && <Card className="p-4 space-y-3"><p role="alert" className="text-sm text-destructive">{error || catalogError}</p><button className={button} onClick={() => { setRevision(value => value + 1); setCatalogRetry(value => value + 1); }}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></Card>}
    {loading ? <p role="status">{msg('FE_LOOKUP_LOADING', 'Loading…')}</p> : !items.length ? <p>{msg('FE_STORE_STOCK_EMPTY', 'No ingredients or supplies have been added for this campus.')}</p> : <div className="grid gap-3 md:grid-cols-2">{items.map(item => <Card className="space-y-3 p-4" key={item.id}><h4 className="font-bold">{item.name}</h4><div className="grid grid-cols-3 gap-2 text-xs">{(kitchen ? [[location(store), item.store_balance]] : [[store ? location(store) : msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen'), store ? item.store_balance : item.central_balance], [msg('FE_STORE_STOCK_ALLOCATED', 'At stores'), item.allocated_balance], [msg('FE_STORE_STOCK_CAMPUS', 'Campus total'), item.current_balance]]).map(([label, value]) => <div className="min-w-0 rounded-xl bg-secondary p-2" key={label}><p className="text-muted-foreground">{label}</p><strong className="mt-1 block break-words">{Number(value).toLocaleString()} {item.usage_unit}</strong></div>)}</div>
      {Number(item.central_balance) < 0 && <p role="alert" className="text-xs text-destructive">{msg('FE_STORE_STOCK_DRIFT', 'Allocated stock exceeds the recorded campus balance. Reconcile the stock ledger before making further movements.')}</p>}
      {!store && <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy || !!item.archived_at} checked={item.store_distributable} onChange={() => classify(item)} />{msg('FE_STORE_STOCK_DISTRIBUTABLE', 'Allocate this item to stores')}</label>}
      {item.store_distributable && !item.archived_at && <div className="flex flex-wrap gap-2">{!kitchen && <button disabled={busy || !store && !stores.some(row => row.is_active)} className="min-h-10 flex items-center gap-2 rounded-full border border-border px-3 text-xs font-bold disabled:opacity-50" onClick={() => open(item, 'transfer')}><ArrowRightLeft className="h-4 w-4" />{msg('FE_STORE_STOCK_TRANSFER', 'Transfer stock')}</button>}{store && (kitchen ? ['usage', 'waste'] : ['usage', 'waste', 'correction']).map(action => <button key={action} disabled={busy} className="min-h-10 rounded-full bg-secondary px-3 text-xs font-bold" onClick={() => open(item, action)}>{actionLabel(action)}</button>)}</div>}
    </Card>)}</div>}
    <button className="min-h-11 rounded-full border border-border px-4 text-sm font-bold" onClick={() => setShowHistory(value => !value)} aria-expanded={showHistory}>{msg('FE_STORE_STOCK_RECENT', 'Recent stock movements')}</button>
    {showHistory && <Card className="space-y-3 p-4">{!history ? <p role="status">{msg('FE_LOOKUP_LOADING', 'Loading…')}</p> : history.error ? <p role="alert">{history.error}</p> : history.entries.map(row => <div className="border-b border-border pb-3 text-sm last:border-0" key={row.id}><strong>{row.item_name}</strong><p className="text-xs text-muted-foreground">{row.store_transfer_id ? `${msg('FE_STORE_STOCK_TRANSFER', 'Transfer stock')}: ${location(row.store_movement?.store_id)} → ${location(row.store_movement?.destination_store_id)}` : actionLabel(row.type)}</p><p>{row.store_name || msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')} · {Number(row.quantity_in_usage_units).toLocaleString()} {row.unit_name}</p><p className="text-xs text-muted-foreground">{row.notes}</p><time className="text-xs text-muted-foreground" dateTime={row.created_at}>{new Date(row.created_at).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })}</time></div>)}</Card>}
    {movement && <Modal open title={movement.item.name} onClose={() => { if (!busy) setMovement(null); }}><form className="space-y-4" onSubmit={save}><p className="text-sm font-bold">{location(store)} · {movement.action === 'transfer' ? msg('FE_STORE_STOCK_TRANSFER', 'Transfer stock') : actionLabel(movement.action)}</p>
      {movement.action === 'transfer' && <label className="block text-sm">{msg('FE_STORE_STOCK_TO', 'Destination')}<select aria-label={msg('FE_STORE_STOCK_TO', 'Destination')} required={!store} className={control} value={movement.destination} onChange={event => setMovement({ ...movement, destination: event.target.value })}>{store && <option value="">{msg('FE_STORE_STOCK_CENTRAL', 'Central kitchen')}</option>}{stores.filter(row => row.id !== store && row.is_active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}
      <label className="block text-sm">{movement.action === 'correction' ? msg('FE_STORE_STOCK_CHANGE', 'Signed change in usage units (positive adds stock)') : msg('FE_STORE_STOCK_QUANTITY', 'Quantity in usage units')}<input required type="number" step="any" min={movement.action === 'correction' ? undefined : '0.000001'} className={control} value={movement.quantity} onChange={event => setMovement({ ...movement, quantity: event.target.value })} /></label>
      <label className="block text-sm">{msg('FE_STORE_STOCK_REASON', 'Reason / dispatch note')}<textarea required maxLength={1000} className={control} value={movement.notes} onChange={event => setMovement({ ...movement, notes: event.target.value })} /></label>{formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}<button disabled={busy} className={`${button} w-full`} type="submit">{msg('FE_STORE_STOCK_SAVE', 'Record movement')}</button></form></Modal>}
  </div>;
}
