import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, Star, CheckSquare, Square, Zap, Gauge, Archive, Layers } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import MenuItemModifiers from './MenuItemModifiers';
import AdminCategories from './AdminCategories';

const BLANK = { name: '', price: '', category_id: '', daily_limit: 50, hp_earn_value: 10, hp_multiplier: 1, description: '', image_url: '', is_featured: false, is_available: true, is_secret: false };

export default function AdminMenu() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [capacityModal, setCapacityModal] = useState(false);
  const [capacity, setCapacity] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [view, setView] = useState('active'); // 'active' | 'archived'
  const [showCats, setShowCats] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const all = view === 'archived'
        ? await mockApi.admin.getArchivedItems()
        : await mockApi.admin.getMenuItems();
      setItems(Array.isArray(all) ? all : (all?.items || []));
    } catch { setItems([]); }
    setLoading(false);
  };
  useEffect(() => { load(); setSelected(new Set()); }, [view]);
  useEffect(() => { (async () => { try { const c = await mockApi.menu.getCategories(); setCategories(Array.isArray(c) ? c : (c?.categories || [])); } catch { setCategories([]); } })(); }, []);

  const save = async () => {
    const body = { ...modal.item, price: Number(modal.item.price), hp_multiplier: Number(modal.item.hp_multiplier) || 1, is_featured: !!modal.item.is_featured, is_available: modal.item.is_available !== false, is_secret: !!modal.item.is_secret };
    try {
      if (modal.isNew) { await mockApi.admin.createMenuItem(body); toast({ title: '✅ Menu item created', description: `"${body.name}" is now live.` }); }
      else { await mockApi.admin.updateMenuItem(modal.item.id, body); toast({ title: '✅ Menu item updated', description: `"${body.name}" saved.` }); }
      setModal(null); await load();
    } catch (e) { toast({ title: 'Failed to save', description: e.message, variant: 'destructive' }); }
  };

  const toggleAvail = async (id) => {
    try { await mockApi.admin.toggleMenuItemAvailability(id); toast({ title: 'Availability toggled' }); await load(); }
    catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
  };

  const remove = async (id) => {
    if (!confirm('Archive this menu item? It moves to the archived list and can be restored from the backend.')) return;
    try { await mockApi.admin.deleteMenuItem(id); toast({ title: 'Item archived' }); await load(); }
    catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
  };

  const toggleSelect = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const bulkToggleAvail = async (makeAvailable) => {
    setBulkBusy(true);
    try {
      await mockApi.admin.bulkToggleMenuItemAvailability([...selected], makeAvailable);
      toast({ title: `✅ ${selected.size} items ${makeAvailable ? 'made available' : 'marked sold out'}` });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: 'Bulk update failed', description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  const bulkAdjustHp = async (multiplier) => {
    setBulkBusy(true);
    try {
      await mockApi.admin.bulkUpdateMenuItemHpMultiplier([...selected], multiplier);
      toast({ title: `✅ HP multiplier set to ${multiplier}× for ${selected.size} items` });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: 'Bulk update failed', description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  // No bulk-delete endpoint — archive each selected item client-side.
  const bulkDelete = async () => {
    if (!confirm(`Archive ${selected.size} selected item(s)?`)) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled([...selected].map((id) => mockApi.admin.deleteMenuItem(id)));
      const ok = results.filter((r) => r.status === 'fulfilled').length;
      toast({ title: `✅ ${ok} item(s) archived`, description: results.length - ok ? `${results.length - ok} failed` : 'All done.' });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: 'Bulk delete failed', description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  const adjustHp = async (id, multiplier, name) => {
    try {
      await mockApi.admin.updateMenuItemHpMultiplier(id, { multiplier });
      toast({ title: '✅ HP multiplier updated', description: `${multiplier === 2 ? 'Double' : 'Half'} HP earning for "${name}".` });
      await load();
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
  };

  const loadCapacity = async () => { setCapacity(await mockApi.admin.getMenuCapacitySettings()); setCapacityModal(true); };
  const saveCapacity = async () => {
    try { await mockApi.admin.updateMenuCapacitySettings(capacity); toast({ title: '✅ Capacity settings saved' }); setCapacityModal(false); }
    catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
  };

  if (loading) return <LoadingSpinner label="Loading menu..." />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="flex gap-1 p-1 rounded-full bg-secondary">
            <button onClick={() => setView('active')} className={`px-3 py-1.5 rounded-full text-xs font-bold ${view === 'active' ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}>Active</button>
            <button onClick={() => setView('archived')} className={`px-3 py-1.5 rounded-full text-xs font-bold flex items-center gap-1 ${view === 'archived' ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}><Archive className="w-3.5 h-3.5" /> Archived</button>
          </div>
          {view === 'active' && selected.size > 0 && <span className="text-xs font-bold text-primary">{selected.size} selected</span>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {view === 'active' && selected.size > 0 && (
            <>
              <button onClick={() => bulkToggleAvail(true)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-green-600 text-white text-xs font-bold disabled:opacity-50"><CheckSquare className="w-3.5 h-3.5" /> Available</button>
              <button onClick={() => bulkToggleAvail(false)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-red-600 text-white text-xs font-bold disabled:opacity-50"><Square className="w-3.5 h-3.5" /> Sold Out</button>
              <button onClick={() => bulkAdjustHp(2)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Zap className="w-3.5 h-3.5" /> 2× HP</button>
              <button onClick={bulkDelete} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-foreground text-white text-xs font-bold disabled:opacity-50"><Trash2 className="w-3.5 h-3.5" /> Delete</button>
            </>
          )}
          {view === 'active' && (
            <>
              <button onClick={() => setShowCats(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-secondary text-foreground text-xs font-bold"><Layers className="w-4 h-4" /> Categories</button>
              <button onClick={() => loadCapacity()} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-secondary text-foreground text-xs font-bold"><Gauge className="w-4 h-4" /> Capacity</button>
              <button onClick={() => setModal({ item: { ...BLANK, category_id: categories[0]?.id || BLANK.category_id }, isNew: true })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add Menu Item</button>
            </>
          )}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12">
          {view === 'archived' ? (
            <><Archive className="w-9 h-9 text-muted-foreground mx-auto mb-2" /><p className="text-sm text-muted-foreground">No archived items.</p></>
          ) : (
            <><Plus className="w-9 h-9 text-muted-foreground mx-auto mb-2" /><p className="text-sm text-muted-foreground">No menu items yet.</p></>
          )}
        </div>
      ) : view === 'archived' ? (
        <div className="space-y-2">
          {items.map((it) => (
            <div key={it.id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-3 opacity-75">
              {it.image_url && <img src={it.image_url} alt={it.name} loading="lazy" decoding="async" className="w-10 h-10 rounded-lg object-cover" />}
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground line-through truncate">{it.name}</div>
                <div className="text-xs text-muted-foreground">{it.menu_categories?.name} · {formatNaira(it.price)}{it.deleted_at ? ` · archived ${new Date(it.deleted_at).toLocaleDateString()}` : ''}</div>
              </div>
              <Pill tone="cocoa">Archived</Pill>
            </div>
          ))}
        </div>
      ) : (
        items.map((it) => (
          <div key={it.id} className={`rounded-2xl bg-white border p-3 flex items-center gap-3 ${selected.has(it.id) ? 'border-primary/60 ring-2 ring-primary/20' : 'border-border'}`}>
            <button onClick={() => toggleSelect(it.id)} className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${selected.has(it.id) ? 'bg-primary border-primary' : 'border-input'}`}>
              {selected.has(it.id) && <CheckSquare className="w-3 h-3 text-white" />}
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-sm text-foreground">{it.name}</span>
                {it.is_featured && <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-400" />}
                {it.is_available ? <Pill tone="green">Live</Pill> : <Pill tone="red">Sold Out</Pill>}
                {it.is_secret && <Pill tone="cocoa">Secret</Pill>}
                {it.hp_multiplier === 0.5 && <Pill tone="amber">½ HP</Pill>}
                {it.hp_multiplier === 2 && <Pill tone="flame">2× HP</Pill>}
              </div>
              <div className="text-xs text-muted-foreground">{it.menu_categories?.name} · {formatNaira(it.price)} · {it.hp_earn_value} HP · Stock {it.daily_remaining}/{it.daily_limit}</div>
            </div>
            <button onClick={() => adjustHp(it.id, 2, it.name)} title="Double HP earn" className="p-1.5 rounded-lg hover:bg-primary/10"><Zap className="w-3.5 h-3.5 text-primary" /></button>
            <Toggle checked={it.is_available} onChange={() => toggleAvail(it.id)} />
            <button onClick={() => setModal({ item: { ...it, price: String(it.price) }, isNew: false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
            <button onClick={() => remove(it.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
          </div>
        ))
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.isNew ? 'New Menu Item' : 'Edit Menu Item'}>
        {modal && (
          <div className="space-y-3">
            <Field label="Name"><TextInput value={modal.item.name} onChange={(e) => setModal({ item: { ...modal.item, name: e.target.value }, isNew: modal.isNew })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Price (₦)"><TextInput type="number" value={modal.item.price} onChange={(e) => setModal({ item: { ...modal.item, price: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label="Category">
                <select value={modal.item.category_id} onChange={(e) => setModal({ item: { ...modal.item, category_id: e.target.value }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  {categories.map((c) => <option key={c.id || c.category_id} value={c.id || c.category_id}>{c.name || c.category_name}</option>)}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Daily Limit"><TextInput type="number" value={modal.item.daily_limit} onChange={(e) => setModal({ item: { ...modal.item, daily_limit: Number(e.target.value) }, isNew: modal.isNew })} /></Field>
              <Field label="HP Earn Value"><TextInput type="number" value={modal.item.hp_earn_value} onChange={(e) => setModal({ item: { ...modal.item, hp_earn_value: Number(e.target.value) }, isNew: modal.isNew })} /></Field>
              <Field label="HP Multiplier" hint="1 = normal, 2 = double, 0.5 = half">
                <select value={modal.item.hp_multiplier} onChange={(e) => setModal({ item: { ...modal.item, hp_multiplier: Number(e.target.value) }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  <option value={1}>1× (normal)</option>
                  <option value={2}>2× (double)</option>
                  <option value={0.5}>0.5× (half)</option>
                </select>
              </Field>
            </div>
            <Field label="Description"><textarea value={modal.item.description} onChange={(e) => setModal({ item: { ...modal.item, description: e.target.value }, isNew: modal.isNew })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
            <Field label="Image"><ImageUploader value={modal.item.image_url} onChange={(url) => setModal({ item: { ...modal.item, image_url: url }, isNew: modal.isNew })} folder="menu_items" /></Field>
            <div className="flex items-center gap-2"><Toggle checked={!!modal.item.is_featured} onChange={(v) => setModal({ item: { ...modal.item, is_featured: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">Featured</span></div>
            <div className="flex items-center gap-2"><Toggle checked={!!modal.item.is_secret} onChange={(v) => setModal({ item: { ...modal.item, is_secret: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">Hidden — only found by search</span></div>

            {/* Per-item variations & add-ons — managed on the same screen as the item */}
            <div className="pt-2 border-t border-border">
              <MenuItemModifiers itemId={modal.isNew ? null : modal.item.id} />
            </div>

            <button onClick={save} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">{modal.isNew ? 'Create Item' : 'Save Changes'}</button>
          </div>
        )}
      </Modal>

      <Modal open={capacityModal} onClose={() => setCapacityModal(false)} title="Capacity Settings">
        {capacity && (
          <div className="space-y-4">
            <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">Three distinct capacity controls. Changes apply site-wide immediately.</div>
            <Field label="Kitchen / Daily Capacity (total orders/day)" hint="Max orders the kitchen accepts per day. Leave blank to remove the daily cap."><TextInput type="number" value={capacity.daily_order_capacity ?? ''} onChange={(e) => setCapacity({ ...capacity, daily_order_capacity: e.target.value === '' ? null : Number(e.target.value) })} /></Field>
            <button onClick={saveCapacity} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Save Capacity Settings</button>
          </div>
        )}
      </Modal>

      <AdminCategories open={showCats} onClose={() => setShowCats(false)} onChanged={load} />
    </div>
  );
}