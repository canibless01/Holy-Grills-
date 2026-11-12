import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { Boxes, Plus, Minus, AlertTriangle, History, PackagePlus, PackageMinus } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import {
  Card,
  Skeleton,
  EmptyState,
  SectionTitle,
  StatTile,
  Modal,
  Field,
  TextInput,
  Pill,
} from './ui/AdminKit';

const AdminStockReport = lazy(() => import('./AdminStockReport'));

const USAGE_TYPES = [
  { id: 'usage', label: msg('FE_STOCK_USAGE', "Usage") },
  { id: 'waste', label: msg('FE_STOCK_WASTE', "Waste") },
  { id: 'correction', label: msg('FE_STOCK_CORRECTION', "Correction") },
];

export default function AdminStore() {
  const { adminCampusId } = useCampus();
  const { user } = useHolyGrill();
  const campusId = user?.role === 'super_admin' ? adminCampusId : user?.campus_id || user?.profile?.campus_id;
  if (!campusId && user?.role === 'super_admin') return <div className="space-y-4"><p className="text-sm text-muted-foreground">{msg('FE_STOCK_SELECT_CAMPUS', 'Select a campus to manage its ingredient stock.')}</p><Suspense fallback={<p role="status">Loading stock report…</p>}><AdminStockReport campusId={null} /></Suspense></div>;
  if (!campusId) return <p className="p-6 text-sm text-muted-foreground">{msg('FE_STOCK_SELECT_CAMPUS', 'Select a campus to manage its ingredient stock.')}</p>;
  return <StockWorkspace key={campusId} campusId={campusId} />;
}

function StockWorkspace({ campusId }) {
  const [showReport, setShowReport] = useState(false);
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [purchaseModal, setPurchaseModal] = useState(null); // item or null
  const [usageModal, setUsageModal] = useState(null);
  const [addModal, setAddModal] = useState(false);
  const [ledgerItem, setLedgerItem] = useState(null);
  const [editItem, setEditItem] = useState(null);
  const [lifecycleItem, setLifecycleItem] = useState(null);
  const [view, setView] = useState('active');

  // Build a {id: name} lookup so stock cards/modals can show the human-readable
  // unit name. The backend returns usage_unit_id / purchase_unit_id (UUIDs), not
  // resolved names — the frontend resolves them from /measurement-units.
  const unitName = useCallback((id) => units.find((u) => u.id === id)?.name, [units]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [stockRes, unitRes] = await Promise.all([
        liveApi.admin.getStockItems({ campus_id: campusId, state: 'all' }),
        liveApi.admin.getMeasurementUnits(),
      ]);
      // unwrap() already extracted the rows (or returned []).
      setItems(stockRes);
      setUnits(Array.isArray(unitRes) ? unitRes : []);
    } catch {
      setLoadError(true);
    }
    setLoading(false);
  }, [campusId]);

  useEffect(() => { load(); }, [load]);

  const activeItems = items.filter(item => !item.archived_at);
  const visibleItems = items.filter(item => view === 'archived' ? !!item.archived_at : !item.archived_at);
  const lowCount = activeItems.filter((i) => i.is_low_stock).length;
  if (loadError) return <div className="text-center py-10 space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button onClick={() => setShowReport(value => !value)} className="rounded-full border border-border px-4 py-2 text-sm font-bold">{showReport ? msg('FE_STOCK_REPORT_HIDE', 'Hide stock report') : msg('FE_STOCK_REPORT_SHOW', 'Stock report & CSV')}</button>
      {showReport && <Suspense fallback={<p role="status">Loading stock report…</p>}><AdminStockReport campusId={campusId} /></Suspense>}
      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Boxes} label={msg('FE_STOCK_TRACKED', "Tracked Items")} value={activeItems.length} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={AlertTriangle} label={msg('FE_STOCK_LOW_STOCK', "Low Stock")} value={lowCount} iconClass="text-destructive" iconBg="bg-destructive/10" />
        <StatTile icon={PackagePlus} label={msg('FE_STOCK_ITEMS_WITH_STOCK', 'Ingredients with stock')} value={activeItems.filter(i => Number(i.current_balance) > 0).length} iconClass="text-success" iconBg="bg-success/15" />
        <StatTile icon={PackageMinus} label={msg('FE_STOCK_TRACKED_UNITS', "Tracked Units")} value={units.length} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle icon={Boxes} title={msg('FE_STOCK_TITLE', "Ingredient Stock")} sub={msg('FE_STOCK_SUBTITLE', "Track purchases, usage, and low-stock alerts")} />
        <div className="flex items-center gap-3">
        <button onClick={load} className="text-xs font-bold text-primary hover:underline">{msg('FE_STOCK_REFRESH', 'Refresh stock')}</button>
        <button
          onClick={() => setAddModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition"
        >
          <Plus className="w-3.5 h-3.5" /> {msg('FE_STOCK_ADD', "Add Item")}
        </button>
        </div>
      </div>

      <div role="group" aria-label={msg('FE_STOCK_TITLE', 'Ingredient Stock')} className="flex flex-wrap gap-2">
        {(['active', 'archived'] as const).map(state => <button key={state} aria-pressed={view === state} onClick={() => setView(state)} className={`px-4 py-2 rounded-full text-xs font-bold ${view === state ? 'bg-primary text-white' : 'bg-secondary text-foreground'}`}>{state === 'active' ? msg('FE_STOCK_ACTIVE', 'Active ingredients') : msg('FE_STOCK_ARCHIVED', 'Archived ingredients')}</button>)}
      </div>
      {/* Items list */}
      {visibleItems.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={Boxes}
            title={view === 'archived' ? msg('FE_STOCK_ARCHIVED_EMPTY', 'No archived ingredients') : msg('FE_STOCK_EMPTY', "No stock items yet")}
            body={view === 'archived' ? msg('FE_STOCK_ARCHIVED_EMPTY_HELP', 'Archived ingredients keep their balances and history here until restored.') : msg('FE_STOCK_EMPTY_HELP', "Add your first ingredient to start tracking purchases and usage.")}
            action={view === 'active' ?
              <button onClick={() => setAddModal(true)} className="px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold">
                {msg('FE_STOCK_ADD_FIRST', "Add First Item")}
              </button> : undefined
            }
          />
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {visibleItems.map((item) => (
            <StockCard
              key={item.id}
              item={item}
              unitName={unitName}
              onPurchase={() => setPurchaseModal(item)}
              onUsage={() => setUsageModal(item)}
              onLedger={() => setLedgerItem(item)}
              onEdit={() => setEditItem(item)}
              onLifecycle={() => setLifecycleItem(item)}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      {lifecycleItem && <StockLifecycleModal item={lifecycleItem} onClose={() => setLifecycleItem(null)} onDone={() => { setLifecycleItem(null); load(); }} />}
      {editItem && <EditItemModal item={editItem} unitName={unitName} onClose={() => setEditItem(null)} onDone={() => { setEditItem(null); load(); }} />}
      {purchaseModal && (
        <PurchaseModal
          item={purchaseModal}
          unitName={unitName}
          onClose={() => setPurchaseModal(null)}
          onDone={() => { setPurchaseModal(null); load(); }}
        />
      )}
      {usageModal && (
        <UsageModal
          item={usageModal}
          unitName={unitName}
          onClose={() => setUsageModal(null)}
          onDone={() => { setUsageModal(null); load(); }}
        />
      )}
      {addModal && (
        <AddItemModal
          units={units}
          campusId={campusId}
          onClose={() => setAddModal(false)}
          onDone={() => { setAddModal(false); setView('active'); load(); }}
        />
      )}
      {ledgerItem && (
        <LedgerModal
          item={ledgerItem}
          unitName={unitName}
          onClose={() => setLedgerItem(null)}
        />
      )}
    </div>
  );
}

// ── Stock card ──
function StockCard({ item, unitName, onPurchase, onUsage, onLedger, onEdit, onLifecycle }) {
  const low = !item.archived_at && item.is_low_stock;
  const usageUnitName = unitName(item.usage_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units');
  return (
    <Card className={`p-4 ${low ? 'border-destructive/40 bg-destructive/5' : ''}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <button onClick={onLedger} className="text-left min-w-0 flex-1 hover:underline">
          <div className="font-bold text-sm text-foreground truncate">{item.name}</div>
        </button>
        {low && <Pill tone="red"><AlertTriangle className="w-2.5 h-2.5" /> {msg('FE_STOCK_LOW', "Low")}</Pill>}
      </div>
      <div className="flex items-baseline gap-1.5 mb-3">
        <span className="font-heading font-extrabold text-2xl text-foreground tabular-nums">
          {item.current_balance ?? 0}
        </span>
        <span className="text-xs text-muted-foreground font-semibold">{usageUnitName}</span>
      </div>
      {item.low_stock_threshold != null && (
        <div className="text-[10px] text-muted-foreground mb-3">{msg('FE_STOCK_THRESHOLD_VALUE', 'Threshold: {threshold} {unit}', { threshold: item.low_stock_threshold, unit: usageUnitName })}</div>
      )}
      <button onClick={onEdit} className="mb-3 text-xs font-bold text-primary hover:underline">{msg('FE_STOCK_EDIT', 'Edit ingredient')}</button>
      <button onClick={onLifecycle} className="ml-3 mb-3 text-xs font-bold text-primary hover:underline">{item.archived_at ? msg('FE_STOCK_RESTORE', 'Restore ingredient') : msg('FE_STOCK_ARCHIVE', 'Archive ingredient')}</button>
      {!item.archived_at && <div className="flex gap-2">
        <button
          onClick={onPurchase}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl bg-success/10 text-success text-xs font-bold hover:bg-success/15 active:scale-95 transition"
        >
          <PackagePlus className="w-3.5 h-3.5" /> {msg('FE_STOCK_PURCHASE', "Purchase")}
        </button>
        <button
          onClick={onUsage}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl bg-secondary text-foreground text-xs font-bold hover:bg-secondary/80 active:scale-95 transition"
        >
          <PackageMinus className="w-3.5 h-3.5" /> {msg('FE_STOCK_USAGE', "Usage")}
        </button>
      </div>}
    </Card>
  );
}

function StockLifecycleModal({ item, onClose, onDone }) {
  const intent = useCmsCreateIntent();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const writing = useRef(false);
  const archived = !item.archived_at;
  const title = archived ? msg('FE_STOCK_ARCHIVE', 'Archive ingredient') : msg('FE_STOCK_RESTORE', 'Restore ingredient');
  const submit = async () => {
    if (writing.current) return;
    writing.current = true; setSaving(true); setError('');
    try {
      await liveApi.admin.archiveStockItem(item.id, intent.body({ archived, expected_version: item.lifecycle_version }));
      intent.clear(); toast({ title: msg('FE_STOCK_LIFECYCLE_SAVED', 'Ingredient updated') }); onDone();
    } catch (e) { setError(e.message || msg('FE_STOCK_LIFECYCLE_FAILED', 'The ingredient could not be updated. Please try again.')); }
    finally { writing.current = false; setSaving(false); }
  };
  return <Modal open onClose={() => { if (!writing.current) onClose(); }} title={title}>
    <div className="space-y-4" aria-busy={saving}>
      <p className="font-bold text-foreground">{item.name}</p>
      <p className="text-sm text-muted-foreground">{archived ? msg('FE_STOCK_ARCHIVE_HELP', 'Archiving stops new purchases and usage. The balance and complete ledger stay available, and you can restore this ingredient later.') : msg('FE_STOCK_RESTORE_HELP', 'Restore this ingredient to the active list. Its existing balance and ledger will be kept.')}</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <button disabled={saving} onClick={submit} className="w-full px-4 py-2 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50">{saving ? msg('FE_STOCK_SAVING', 'Saving…') : title}</button>
    </div>
  </Modal>;
}

function EditItemModal({ item, unitName, onClose, onDone }) {
  const [name, setName] = useState(item.name);
  const [threshold, setThreshold] = useState(String(item.low_stock_threshold));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const writing = useRef(false);
  const submit = async (event) => {
    event.preventDefault();
    if (writing.current) return;
    if (!name.trim() || name.trim().length > 128) { setError(msg('FE_STOCK_NAME_INVALID', 'Enter a name between 1 and 128 characters.')); return; }
    const value = threshold.trim() ? Number(threshold) : NaN;
    if (!Number.isFinite(value) || value < 0) { setError(msg('FE_STOCK_THRESHOLD_INVALID', 'Enter a finite, non-negative threshold.')); return; }
    writing.current = true; setSaving(true); setError('');
    try {
      await liveApi.admin.updateStockItem(item.id, {
        name: name.trim(), low_stock_threshold: value,
        expected: { name: item.name, low_stock_threshold: Number(item.low_stock_threshold) },
      });
      toast({ title: msg('FE_STOCK_EDIT_SAVED', 'Ingredient saved') });
      onDone();
    } catch (e) { setError(e.message || msg('FE_STOCK_EDIT_FAILED', 'The ingredient could not be saved. Please try again.')); }
    finally { writing.current = false; setSaving(false); }
  };
  return <Modal open onClose={() => { if (!writing.current) onClose(); }} title={msg('FE_STOCK_EDIT', 'Edit ingredient')}>
    <form onSubmit={submit} aria-busy={saving} className="space-y-3">
      <Field label={msg('FE_STOCK_NAME', 'Name')}><TextInput aria-label={msg('FE_STOCK_NAME', 'Name')} value={name} maxLength={128} disabled={saving} onChange={e => setName(e.target.value)} /></Field>
      <Field label={msg('FE_STOCK_THRESHOLD', 'Low Stock Threshold')} hint={unitName(item.usage_unit_id)}><TextInput aria-label={msg('FE_STOCK_THRESHOLD', 'Low Stock Threshold')} type="number" inputMode="decimal" min="0" step="any" value={threshold} disabled={saving} onChange={e => setThreshold(e.target.value)} /></Field>
      <p className="text-xs text-muted-foreground">{msg('FE_STOCK_EDIT_UNITS_FIXED', 'Units and conversion stay fixed so recorded purchases and usage keep their meaning. Use the ledger to correct quantities.')}</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <button type="submit" disabled={saving} className="w-full px-4 py-2 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50">{saving ? msg('FE_STOCK_SAVING', 'Saving…') : msg('FE_STOCK_EDIT_SAVE', 'Save ingredient')}</button>
    </form>
  </Modal>;
}

// ── Purchase modal ──
function PurchaseModal({ item, unitName, onClose, onDone }) {
  const intent = useCmsCreateIntent();
  const [qty, setQty] = useState('');
  const [cost, setCost] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const writing = useRef(false);
  const [err, setErr] = useState('');
  const purchaseUnitName = unitName(item.purchase_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units');

  const submit = async () => {
    if (writing.current) return;
    const quantity = Number(qty);
    if (!qty.trim() || !Number.isFinite(quantity) || quantity <= 0) { setErr(msg('FE_STOCK_POSITIVE_QUANTITY', 'Enter a finite quantity greater than zero.')); return; }
    if (cost.trim() && (!Number.isFinite(Number(cost)) || Number(cost) < 0)) { setErr(msg('FE_STOCK_COST_INVALID', 'Enter a finite, non-negative cost.')); return; }
    writing.current = true; setSaving(true); setErr('');
    try {
      await liveApi.admin.logStockPurchase(item.id, intent.body({
        quantity,
        cost: cost.trim() ? Number(cost) : null,
        notes: notes.trim() || undefined,
      }));
      intent.clear();
      toast({ title: msg('FE_ADMIN_STORE_PURCHASE_LOGGED', '✓ Purchase logged'), description: msg('FE_ADMIN_STORE_QUANTITY_PURCHASE_UNIT_NAME_ADDED_TO', '{quantity} {purchase_unit_name} added to {name}', { quantity: quantity, purchase_unit_name: purchaseUnitName, name: item.name }) });
      onDone();
    } catch (e) { setErr(e.message || msg('FE_STOCK_PURCHASE_FAILED', "Failed to log purchase")); }
    writing.current = false; setSaving(false);
  };

  return (
    <Modal open onClose={saving ? () => {} : onClose} title={msg('FE_STOCK_PURCHASE_TITLE', 'Log Purchase — {name}', { name: item.name })}>
      <div className="space-y-3">
        <Field label={msg('FE_STOCK_QUANTITY_LABEL', 'Quantity ({unit})', { unit: purchaseUnitName })} hint={msg('FE_STOCK_PURCHASE_QTY_HELP', "How many did you buy?")}>
          <TextInput aria-label={msg('FE_STOCK_QUANTITY', 'Quantity')} type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} placeholder={msg('FE_STOCK_EXAMPLE_TEN', "e.g. 10")} autoFocus />
        </Field>
        <Field label={msg('FE_STOCK_COST_LABEL', "Cost (₦)")} hint={msg('FE_STOCK_COST_HELP', "Total purchase cost, optional")}>
          <TextInput aria-label={msg('FE_STOCK_COST_LABEL', 'Cost (₦)')} type="number" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} placeholder={msg('FE_STOCK_EXAMPLE_COST', "e.g. 5000")} />
        </Field>
        <Field label={msg('FE_STOCK_NOTES', "Notes (optional)")}>
          <TextInput aria-label={msg('FE_STOCK_NOTES', 'Notes (optional)')} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={msg('FE_STOCK_SUPPLIER_PLACEHOLDER', "Supplier, receipt no, etc.")} />
        </Field>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? msg('FE_STOCK_SAVING', "Saving…") : msg('FE_STOCK_PURCHASE_SAVE', "Log Purchase")}
        </button>
      </div>
    </Modal>
  );
}

// ── Usage modal ──
function UsageModal({ item, unitName, onClose, onDone }) {
  const intent = useCmsCreateIntent();
  const [qty, setQty] = useState('');
  const [type, setType] = useState('usage');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const writing = useRef(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (writing.current) return;
    const quantity = Number(qty);
    if (!qty.trim() || !Number.isFinite(quantity) || (type === 'correction' ? quantity === 0 : quantity <= 0)) { setErr(type === 'correction' ? msg('FE_STOCK_CORRECTION_INVALID', 'Enter a finite, non-zero correction.') : msg('FE_STOCK_POSITIVE_QUANTITY', 'Enter a finite quantity greater than zero.')); return; }
    writing.current = true; setSaving(true); setErr('');
    try {
      await liveApi.admin.logStockUsage(item.id, intent.body({
        quantity,
        type,
        notes: notes.trim() || undefined,
      }));
      intent.clear();
      toast({
        title: msg('FE_ADMIN_STORE_USAGE_LOGGED', '✓ Usage logged'),
        description: msg('FE_ADMIN_STORE_USAGE_LOGGED_BODY', '{quantity} {unit} of {name}', {
          quantity,
          unit: unitName(item.usage_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units'),
          name: item.name,
        }),
      });
      onDone();
    } catch (e) { setErr(e.message || msg('FE_STOCK_USAGE_FAILED', "Failed to log usage")); }
    writing.current = false; setSaving(false);
  };

  return (
    <Modal open onClose={saving ? () => {} : onClose} title={msg('FE_STOCK_USAGE_TITLE', 'Log Usage — {name}', { name: item.name })}>
      <div className="space-y-3">
        <Field label={msg('FE_STOCK_QUANTITY_LABEL', 'Quantity ({unit})', { unit: unitName(item.usage_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units') })} hint={msg('FE_STOCK_USAGE_QTY_HELP', "How many were used?")}>
          <TextInput aria-label={msg('FE_STOCK_QUANTITY', 'Quantity')} type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} placeholder={msg('FE_STOCK_EXAMPLE_FIVE', "e.g. 5")} autoFocus />
        </Field>
        <Field label={msg('FE_STOCK_TYPE', "Type")}>
          <div className="flex gap-2 mt-1">
            {USAGE_TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => setType(t.id)}
                className={`flex-1 py-2 rounded-xl text-xs font-bold border transition ${type === t.id ? 'bg-primary text-white border-primary' : 'bg-card border-border text-muted-foreground'}`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </Field>
        {type === 'correction' && <p className="text-xs text-muted-foreground">{msg('FE_STOCK_CORRECTION_HELP', 'Positive corrections remove usage units; negative corrections add usage units. The ledger records the change.')}</p>}
        <Field label={msg('FE_STOCK_NOTES', "Notes (optional)")}>
          <TextInput aria-label={msg('FE_STOCK_NOTES', 'Notes (optional)')} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={msg('FE_STOCK_REASON_PLACEHOLDER', "Reason, batch, etc.")} />
        </Field>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? msg('FE_STOCK_SAVING', "Saving…") : msg('FE_STOCK_USAGE_SAVE', "Log Usage")}
        </button>
      </div>
    </Modal>
  );
}

// ── Add item modal ──
function AddItemModal({ onClose, onDone, units = [], campusId }: {
  onClose?: () => void;
  onDone?: () => void;
  units?: { id: string; name: string }[];
  campusId: string;
}) {
  const intent = useCmsCreateIntent();
  const [name, setName] = useState('');
  const [purchaseUnitId, setPurchaseUnitId] = useState('');
  const [usageUnitId, setUsageUnitId] = useState('');
  const [conversionFactor, setConversionFactor] = useState('');
  const [threshold, setThreshold] = useState('');
  const [saving, setSaving] = useState(false);
  const writing = useRef(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (writing.current) return;
    if (!name.trim() || name.trim().length > 128) { setErr(msg('FE_STOCK_NAME_INVALID', 'Enter a name between 1 and 128 characters.')); return; }
    if (!usageUnitId) { setErr(msg('FE_STOCK_USAGE_UNIT_REQUIRED', 'Select a usage unit.')); return; }
    const conversion = conversionFactor.trim() ? Number(conversionFactor) : 1;
    const lowThreshold = threshold.trim() ? Number(threshold) : 0;
    if (!Number.isFinite(conversion) || conversion <= 0 || !Number.isFinite(lowThreshold) || lowThreshold < 0) { setErr(msg('FE_STOCK_UNITS_INVALID', 'Conversion must be positive and the threshold must be non-negative.')); return; }
    writing.current = true; setSaving(true); setErr('');
    try {
      await liveApi.admin.createStockItem(intent.body({
        campus_id: campusId,
        name: name.trim(),
        purchase_unit_id: purchaseUnitId || usageUnitId,
        usage_unit_id: usageUnitId,
        conversion_factor: conversion,
        low_stock_threshold: lowThreshold,
      }));
      intent.clear();
      toast({ title: msg('FE_ADMIN_STORE_ITEM_ADDED', '✓ Item added'), description: msg('FE_ADMIN_STORE_NAME_IS_NOW_TRACKED', '{name} is now tracked', { name: name.trim() }) });
      onDone();
    } catch (e) { setErr(e.message || msg('FE_STOCK_ADD_FAILED', "Failed to add item")); }
    writing.current = false; setSaving(false);
  };

  return (
    <Modal open onClose={saving ? () => {} : onClose} title={msg('FE_STOCK_ADD_TITLE', "Add Stock Item")}>
      <div className="space-y-3">
        <Field label={msg('FE_STOCK_NAME', "Name")} hint={msg('FE_STOCK_NAME_HELP', "e.g. Spices, Oil, Spoons")}>
          <TextInput aria-label={msg('FE_STOCK_NAME', 'Name')} maxLength={128} value={name} onChange={(e) => setName(e.target.value)} placeholder={msg('FE_STOCK_NAME_PLACEHOLDER', "Ingredient name")} autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_STOCK_PURCHASE_UNIT', "Purchase Unit")} hint={msg('FE_STOCK_PURCHASE_UNIT_HELP', "Unit the item is bought in")}>
            <select
              aria-label={msg('FE_STOCK_PURCHASE_UNIT', 'Purchase Unit')}
              value={purchaseUnitId}
              onChange={(e) => setPurchaseUnitId(e.target.value)}
              disabled={!units.length || saving}
              className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm text-foreground disabled:opacity-50"
            >
              <option value="">{msg('FE_STOCK_SELECT_UNIT', "Select unit")}</option>
              {(units || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
          <Field label={msg('FE_STOCK_USAGE_UNIT', "Usage Unit")} hint={msg('FE_STOCK_USAGE_UNIT_HELP', "Unit the item is counted in")}>
            <select
              aria-label={msg('FE_STOCK_USAGE_UNIT', 'Usage Unit')}
              value={usageUnitId}
              onChange={(e) => setUsageUnitId(e.target.value)}
              disabled={!units.length || saving}
              className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm text-foreground disabled:opacity-50"
            >
              <option value="">{msg('FE_STOCK_SELECT_UNIT', "Select unit")}</option>
              {(units || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label={msg('FE_STOCK_CONVERSION', "Conversion Factor")} hint={msg('FE_STOCK_CONVERSION_HELP', "Units per purchase unit")}>
            <TextInput aria-label={msg('FE_STOCK_CONVERSION', 'Conversion Factor')} type="number" inputMode="decimal" value={conversionFactor} onChange={(e) => setConversionFactor(e.target.value)} placeholder={msg('FE_STOCK_EXAMPLE_CONVERSION', "e.g. 40")} />
          </Field>
          <Field label={msg('FE_STOCK_THRESHOLD', "Low Stock Threshold")} hint={msg('FE_STOCK_THRESHOLD_HELP', "In usage units")}>
            <TextInput aria-label={msg('FE_STOCK_THRESHOLD', 'Low Stock Threshold')} type="number" inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder={msg('FE_STOCK_EXAMPLE_THRESHOLD', "e.g. 20")} />
          </Field>
        </div>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving || !units.length} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? msg('FE_STOCK_SAVING', "Saving…") : msg('FE_STOCK_ADD', "Add Item")}
        </button>
      </div>
    </Modal>
  );
}

// ── Ledger modal ──
function LedgerModal({ item, unitName, onClose }) {
  const [entries, setEntries] = useState([]);
  const [page, setPage] = useState(0);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError(false);
    try {
      const value = await liveApi.admin.getStockItemLedgerPage(item.id, { limit: 50, offset: page * 50 });
      if (current !== generation.current) return;
      setEntries(value.ledger || []); setMore(!!value.has_more);
    } catch { if (current === generation.current) { setError(true); setEntries([]); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [item.id, page]);
  useEffect(() => { void load(); return () => { ++generation.current; }; }, [load]);
  return <Modal open onClose={onClose} title={msg('FE_STOCK_LEDGER_TITLE', 'Ledger — {name}', { name: item.name })}>
    {loading ? <p role="status">{msg('FE_ADMIN_FLAGS_LOADING', 'Loading…')}</p>
      : error ? <div role="alert"><p>{msg('FE_STOCK_LEDGER_FAILED', 'Stock history could not be loaded.')}</p><button className="mt-2 font-bold text-primary" onClick={load}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>
      : entries.length === 0 ? <EmptyState icon={History} title={msg('FE_STOCK_LEDGER_EMPTY', 'No entries yet')} body={msg('FE_STOCK_LEDGER_EMPTY_HELP', 'Purchases and adjustments appear here, newest first.')} />
      : <div className="space-y-2">{entries.map(e => {
        const delta = Number(e.quantity_in_usage_units || 0);
        const purchase = e.type === 'purchase';
        return <div key={e.id} className="flex gap-3 p-3 rounded-xl bg-secondary/50 border border-border">
          <div className="w-8 h-8 shrink-0 flex items-center justify-center">{delta >= 0 ? <Plus className="w-4 h-4 text-success" /> : <Minus className="w-4 h-4 text-destructive" />}</div>
          <div className="min-w-0 text-xs space-y-1">
            <p className="text-sm font-bold capitalize">{e.type}</p>
            <p>{e.quantity_entered} {e.measurement_units?.name || unitName(e.unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units')}</p>
            <p>{msg('FE_STOCK_LEDGER_CHANGE', 'Balance change: {delta} {unit}', { delta: `${delta > 0 ? '+' : ''}${delta}`, unit: unitName(item.usage_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units') })}</p>
            {purchase && e.cost != null && <p>{msg('FE_STOCK_LEDGER_COST', 'Purchase cost: ₦{cost}', { cost: Number(e.cost).toLocaleString() })}</p>}
            <p className="text-muted-foreground">{e.profiles?.full_name || '—'} · {new Date(e.created_at).toLocaleString()}</p>
            {e.notes && <p className="italic break-words">{e.notes}</p>}
          </div>
        </div>;
      })}</div>}
    {!loading && !error && <div className="mt-3 flex items-center justify-between gap-3">
      <button disabled={page === 0} onClick={() => setPage(value => value - 1)} className="font-bold text-primary disabled:opacity-40">{msg('FE_STOCK_PREVIOUS', 'Previous')}</button>
      <span className="text-xs">{msg('FE_STOCK_PAGE', 'Page {number}', { number: page + 1 })}</span>
      <button disabled={!more} onClick={() => setPage(value => value + 1)} className="font-bold text-primary disabled:opacity-40">{msg('FE_STOCK_NEXT', 'Next')}</button>
    </div>}
  </Modal>;
}
