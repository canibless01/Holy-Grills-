import { useState, useEffect, useCallback } from 'react';
import { Boxes, Plus, Minus, AlertTriangle, History, PackagePlus, PackageMinus } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
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

const USAGE_TYPES = [
  { id: 'usage', label: 'Usage' },
  { id: 'waste', label: 'Waste' },
  { id: 'correction', label: 'Correction' },
];

export default function AdminStore() {
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [purchaseModal, setPurchaseModal] = useState(null); // item or null
  const [usageModal, setUsageModal] = useState(null);
  const [addModal, setAddModal] = useState(false);
  const [ledgerItem, setLedgerItem] = useState(null);

  // Build a {id: name} lookup so stock cards/modals can show the human-readable
  // unit name. The backend returns usage_unit_id / purchase_unit_id (UUIDs), not
  // resolved names — the frontend resolves them from /measurement-units.
  const unitName = useCallback((id) => units.find((u) => u.id === id)?.name, [units]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [stockRes, unitRes] = await Promise.all([
        liveApi.admin.getStockItems(),
        liveApi.admin.getMeasurementUnits().catch(() => []),
      ]);
      // unwrap() already extracted the rows (or returned []).
      setItems(stockRes);
      setUnits(Array.isArray(unitRes) ? unitRes : []);
    } catch {
      setItems([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const lowCount = items.filter((i) => i.is_low_stock).length;

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
      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Boxes} label="Tracked Items" value={items.length} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={AlertTriangle} label="Low Stock" value={lowCount} iconClass="text-destructive" iconBg="bg-destructive/10" />
        <StatTile icon={PackagePlus} label="In Stock" value={items.reduce((s, i) => s + (Number(i.current_balance) || 0), 0)} iconClass="text-success" iconBg="bg-success/15" />
        <StatTile icon={PackageMinus} label="Tracked Units" value={units.length} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <SectionTitle icon={Boxes} title="Ingredient Stock" sub="Track purchases, usage, and low-stock alerts" />
        <button
          onClick={() => setAddModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition"
        >
          <Plus className="w-3.5 h-3.5" /> Add Item
        </button>
      </div>

      {/* Items list */}
      {items.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={Boxes}
            title="No stock items yet"
            body="Add your first ingredient to start tracking purchases and usage."
            action={
              <button onClick={() => setAddModal(true)} className="px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold">
                Add First Item
              </button>
            }
          />
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((item) => (
            <StockCard
              key={item.id}
              item={item}
              unitName={unitName}
              onPurchase={() => setPurchaseModal(item)}
              onUsage={() => setUsageModal(item)}
              onLedger={() => setLedgerItem(item)}
            />
          ))}
        </div>
      )}

      {/* Modals */}
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
          onClose={() => setAddModal(false)}
          onDone={() => { setAddModal(false); load(); }}
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
function StockCard({ item, unitName, onPurchase, onUsage, onLedger }) {
  const low = item.is_low_stock;
  const usageUnitName = unitName(item.usage_unit_id) || 'units';
  return (
    <Card className={`p-4 ${low ? 'border-destructive/40 bg-destructive/5' : ''}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <button onClick={onLedger} className="text-left min-w-0 flex-1 hover:underline">
          <div className="font-bold text-sm text-foreground truncate">{item.name}</div>
        </button>
        {low && <Pill tone="red"><AlertTriangle className="w-2.5 h-2.5" /> Low</Pill>}
      </div>
      <div className="flex items-baseline gap-1.5 mb-3">
        <span className="font-heading font-extrabold text-2xl text-foreground tabular-nums">
          {item.current_balance ?? 0}
        </span>
        <span className="text-xs text-muted-foreground font-semibold">{usageUnitName}</span>
      </div>
      {item.low_stock_threshold != null && (
        <div className="text-[10px] text-muted-foreground mb-3">Threshold: {item.low_stock_threshold} {usageUnitName}</div>
      )}
      <div className="flex gap-2">
        <button
          onClick={onPurchase}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl bg-success/10 text-success text-xs font-bold hover:bg-success/15 active:scale-95 transition"
        >
          <PackagePlus className="w-3.5 h-3.5" /> Purchase
        </button>
        <button
          onClick={onUsage}
          className="flex-1 flex items-center justify-center gap-1 py-2 rounded-xl bg-secondary text-foreground text-xs font-bold hover:bg-secondary/80 active:scale-95 transition"
        >
          <PackageMinus className="w-3.5 h-3.5" /> Usage
        </button>
      </div>
    </Card>
  );
}

// ── Purchase modal ──
function PurchaseModal({ item, unitName, onClose, onDone }) {
  const [qty, setQty] = useState('');
  const [cost, setCost] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const purchaseUnitName = unitName(item.purchase_unit_id) || 'units';

  const submit = async () => {
    const quantity = parseFloat(qty);
    if (!quantity || quantity <= 0) { setErr('Enter a valid quantity'); return; }
    setSaving(true); setErr('');
    try {
      await liveApi.admin.logStockPurchase(item.id, {
        quantity,
        cost: cost ? parseFloat(cost) : 0,
        notes: notes.trim() || undefined,
      });
      toast({ title: msg('FE_ADMIN_STORE_PURCHASE_LOGGED', '✓ Purchase logged'), description: msg('FE_ADMIN_STORE_QUANTITY_PURCHASE_UNIT_NAME_ADDED_TO', '{quantity} {purchase_unit_name} added to {name}', { quantity: quantity, purchase_unit_name: purchaseUnitName, name: item.name }) });
      onDone();
    } catch (e) { setErr(e.message || 'Failed to log purchase'); }
    setSaving(false);
  };

  return (
    <Modal open onClose={onClose} title={`Log Purchase — ${item.name}`}>
      <div className="space-y-3">
        <Field label={`Quantity (${purchaseUnitName})`} hint="How many did you buy?">
          <TextInput type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="e.g. 10" autoFocus />
        </Field>
        <Field label="Cost (₦)" hint="Total purchase cost, optional">
          <TextInput type="number" inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="e.g. 5000" />
        </Field>
        <Field label="Notes (optional)">
          <TextInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Supplier, receipt no, etc." />
        </Field>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? 'Saving…' : 'Log Purchase'}
        </button>
      </div>
    </Modal>
  );
}

// ── Usage modal ──
function UsageModal({ item, unitName, onClose, onDone }) {
  const [qty, setQty] = useState('');
  const [type, setType] = useState('usage');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    const quantity = parseFloat(qty);
    if (!quantity || quantity <= 0) { setErr('Enter a valid quantity'); return; }
    setSaving(true); setErr('');
    try {
      await liveApi.admin.logStockUsage(item.id, {
        quantity,
        type,
        notes: notes.trim() || undefined,
      });
      toast({
        title: msg('FE_ADMIN_STORE_USAGE_LOGGED', '✓ Usage logged'),
        description: msg('FE_ADMIN_STORE_USAGE_LOGGED_BODY', '{quantity} {unit} of {name}', {
          quantity,
          unit: unitName(item.usage_unit_id) || msg('FE_ADMIN_STORE_UNITS', 'units'),
          name: item.name,
        }),
      });
      onDone();
    } catch (e) { setErr(e.message || 'Failed to log usage'); }
    setSaving(false);
  };

  return (
    <Modal open onClose={onClose} title={`Log Usage — ${item.name}`}>
      <div className="space-y-3">
        <Field label={`Quantity (${unitName(item.usage_unit_id) || 'units'})`} hint="How many were used?">
          <TextInput type="number" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="e.g. 5" autoFocus />
        </Field>
        <Field label="Type">
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
        <Field label="Notes (optional)">
          <TextInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason, batch, etc." />
        </Field>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? 'Saving…' : 'Log Usage'}
        </button>
      </div>
    </Modal>
  );
}

// ── Add item modal ──
function AddItemModal({ onClose, onDone }: {
  onClose?: () => void;
  onDone?: () => void;
  /** Caller passes its cached units; this modal loads its own on open. */
  units?: unknown;
}) {
  const [name, setName] = useState('');
  const [units, setUnits] = useState(null); // null = loading, [] = none configured
  const [purchaseUnitId, setPurchaseUnitId] = useState('');
  const [usageUnitId, setUsageUnitId] = useState('');
  const [conversionFactor, setConversionFactor] = useState('');
  const [threshold, setThreshold] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // Units load when THIS form opens (not on page load) — GET /measurement-units.
  useEffect(() => {
    liveApi.admin.getMeasurementUnits()
      .then((list) => setUnits(Array.isArray(list) ? list : []))
      .catch(() => setUnits([]));
  }, []);

  const submit = async () => {
    if (!name.trim()) { setErr('Name is required'); return; }
    if (!usageUnitId) { setErr('Usage unit is required'); return; }
    setSaving(true); setErr('');
    try {
      await liveApi.admin.createStockItem({
        name: name.trim(),
        purchase_unit_id: purchaseUnitId || undefined,
        usage_unit_id: usageUnitId,
        conversion_factor: conversionFactor ? parseFloat(conversionFactor) : undefined,
        low_stock_threshold: threshold ? parseFloat(threshold) : undefined,
      });
      toast({ title: msg('FE_ADMIN_STORE_ITEM_ADDED', '✓ Item added'), description: msg('FE_ADMIN_STORE_NAME_IS_NOW_TRACKED', '{name} is now tracked', { name: name.trim() }) });
      onDone();
    } catch (e) { setErr(e.message || 'Failed to add item'); }
    setSaving(false);
  };

  return (
    <Modal open onClose={onClose} title="Add Stock Item">
      <div className="space-y-3">
        <Field label="Name" hint="e.g. Spices, Oil, Spoons">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Ingredient name" autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Purchase Unit" hint="Unit the item is bought in">
            <select
              value={purchaseUnitId}
              onChange={(e) => setPurchaseUnitId(e.target.value)}
              disabled={units == null}
              className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm text-foreground disabled:opacity-50"
            >
              <option value="">{units == null ? 'Loading units…' : 'Select unit'}</option>
              {(units || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
          <Field label="Usage Unit" hint="Unit the item is counted in">
            <select
              value={usageUnitId}
              onChange={(e) => setUsageUnitId(e.target.value)}
              disabled={units == null}
              className="w-full mt-1 p-2.5 rounded-xl border border-border bg-card text-sm text-foreground disabled:opacity-50"
            >
              <option value="">{units == null ? 'Loading units…' : 'Select unit'}</option>
              {(units || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Conversion Factor" hint="Units per purchase unit">
            <TextInput type="number" inputMode="decimal" value={conversionFactor} onChange={(e) => setConversionFactor(e.target.value)} placeholder="e.g. 40" />
          </Field>
          <Field label="Low Stock Threshold" hint="In usage units">
            <TextInput type="number" inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder="e.g. 20" />
          </Field>
        </div>
        {err && <p className="text-xs font-bold text-destructive">{err}</p>}
        <button onClick={submit} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">
          {saving ? 'Saving…' : 'Add Item'}
        </button>
      </div>
    </Modal>
  );
}

// ── Ledger modal ──
function LedgerModal({ item, unitName, onClose }) {
  const [entries, setEntries] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await liveApi.admin.getStockItemLedger(item.id);
        // unwrap() already handles the entries/ledger/transactions keys.
        setEntries(res);
      } catch { setEntries([]); }
      setLoading(false);
    })();
  }, [item.id]);

  return (
    <Modal open onClose={onClose} title={`Ledger — ${item.name}`}>
      {loading ? (
        <div className="py-8 flex justify-center"><div className="w-6 h-6 border-2 border-border border-t-primary rounded-full animate-spin" /></div>
      ) : !entries || entries.length === 0 ? (
        <EmptyState icon={History} title="No entries yet" body="Purchases and usage will appear here in reverse order." />
      ) : (
        <div className="space-y-2">
          {entries.map((e, i) => {
            const isPurchase = (e.type || e.entry_type) === 'purchase';
            const qty = e.quantity ?? e.qty ?? 0;
            return (
              <div key={e.id || i} className="flex items-center gap-3 p-3 rounded-xl bg-secondary/50 border border-border">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isPurchase ? 'bg-success/15' : 'bg-accent/25'}`}>
                  {isPurchase ? <Plus className="w-4 h-4 text-success" /> : <Minus className="w-4 h-4 text-accent-foreground" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-foreground capitalize">{e.type || e.entry_type || 'usage'}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {qty} {unitName(item.usage_unit_id) || 'units'} · {e.logged_by || e.created_by || '—'} · {new Date(e.created_at || e.logged_at).toLocaleString()}
                  </div>
                  {e.notes && <div className="text-[11px] text-muted-foreground mt-0.5 italic">"{e.notes}"</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}