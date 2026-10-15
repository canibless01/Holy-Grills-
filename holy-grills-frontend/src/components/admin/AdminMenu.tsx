import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect, useRef } from 'react';
import { Plus, Pencil, Trash2, Star, CheckSquare, Square, Zap, Gauge, Layers } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import MenuItemModifiers from './MenuItemModifiers';
import AdminCategories from './AdminCategories';
import { msg, useMessages } from '@/lib/messages';
import { useIsSuperAdmin } from './SuperAdminGate';
import { useCampus } from '@/lib/campusContext';
import { apiClient } from '@/lib/apiClient';

const BLANK = { name: '', price: '', category_id: '', daily_limit: 50, hp_earn_value: 10, hp_multiplier: 1, description: '', image_url: '', is_featured: false, is_available: true, is_secret: false };

export default function AdminMenu() {
  useMessages();
  const isSuperAdmin = useIsSuperAdmin();
  const { adminCampusId } = useCampus();
  const [override, setOverride] = useState(null);
  const [overrideBusy, setOverrideBusy] = useState(false);
  const openOverride = item => setOverride({ item, is_available: item.campus_availability?.is_available ?? true,
    daily_limit: item.campus_availability?.daily_limit ?? '', price_override: item.campus_availability?.price_override ?? '',
    opens_at: item.campus_availability?.opens_at ?? '', closes_at: item.campus_availability?.closes_at ?? '' });
  const saveOverride = async () => {
    setOverrideBusy(true);
    try {
      await apiClient.patch(`/menu/items/${override.item.id}/availability`, { is_available: override.is_available,
        daily_limit: override.daily_limit === '' ? null : Number(override.daily_limit),
        price_override: override.price_override === '' ? null : Number(override.price_override),
        opens_at: override.opens_at || null, closes_at: override.closes_at || null });
      setOverride(null); await load();
      toast({ title: msg('FE_ADMIN_MENU_CAMPUS_MENU_SETTINGS_SAVED', 'Campus menu settings saved') });
    } catch (error) { toast({ title: msg('FE_ADMIN_MENU_COULD_NOT_SAVE_CAMPUS_SETTINGS', 'Could not save campus settings'), description: error.message, variant: 'destructive' }); }
    finally { setOverrideBusy(false); }
  };
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [capacityModal, setCapacityModal] = useState(false);
  const [capacity, setCapacity] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [showCats, setShowCats] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      // F5 GAP (reported): the "Archived" view used GET /items/archived, which no
      // backend route serves (menu.py filters is_archived but never lists archived
      // rows), so it always rendered empty. Archived rows stay in the database; the
      // view comes back when the backend route exists.
      const all = await mockApi.admin.getMenuItems();
      // unwrap() already extracted the rows (or returned []).
      setItems(all);
    } catch { setItems([]); }
    setLoading(false);
  };
  useEffect(() => { load(); setSelected(new Set()); }, []);
  useEffect(() => { (async () => { try { const c = await mockApi.menu.getCategories(); setCategories(Array.isArray(c) ? c : (c?.categories || [])); } catch { setCategories([]); } })(); }, []);

  const saveInFlight = useRef(false);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (saveInFlight.current) return;
    saveInFlight.current = true; setSaving(true);
    const body = { ...modal.item, price: Number(modal.item.price), hp_multiplier: Number(modal.item.hp_multiplier) || 1, is_featured: !!modal.item.is_featured, is_available: modal.item.is_available !== false, is_secret: !!modal.item.is_secret };
    try {
      if (modal.isNew) { await mockApi.admin.createMenuItem(body); toast({ title: msg('FE_ADMIN_MENU_MENU_ITEM_CREATED', '✅ Menu item created'), description: msg('FE_ADMIN_MENU_NAME_IS_NOW_LIVE', '"{name}" is now live.', { name: body.name }) }); }
      else { await mockApi.admin.updateMenuItem(modal.item.id, body); toast({ title: msg('FE_ADMIN_MENU_MENU_ITEM_UPDATED', '✅ Menu item updated'), description: msg('FE_ADMIN_MENU_NAME_SAVED', '"{name}" saved.', { name: body.name }) }); }
      setModal(null); await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_MENU_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' }); }
    finally { saveInFlight.current = false; setSaving(false); }
  };

  const toggleAvail = async (id) => {
    try { await mockApi.admin.toggleMenuItemAvailability(id); toast({ title: msg('FE_ADMIN_MENU_AVAILABILITY_TOGGLED', 'Availability toggled') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_MENU_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  const remove = async (id) => {
    if (!(await confirmAction({ title: "Archive this menu item?", body: "It disappears from the menu; existing orders keep their details.", destructive: true, confirmLabel: "Archive" }))) return;
    try { await mockApi.admin.deleteMenuItem(id); toast({ title: msg('FE_ADMIN_MENU_ITEM_ARCHIVED', 'Item archived') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_MENU_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
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
      const count = selected.size;
      toast({
        title: makeAvailable
          ? (count === 1
            ? msg('FE_ADMIN_MENU_ONE_ITEM_MADE_AVAILABLE', '✅ 1 item made available')
            : msg('FE_ADMIN_MENU_ITEMS_MADE_AVAILABLE', '✅ {count} items made available', { count }))
          : (count === 1
            ? msg('FE_ADMIN_MENU_ONE_ITEM_MARKED_SOLD_OUT', '✅ 1 item marked sold out')
            : msg('FE_ADMIN_MENU_ITEMS_MARKED_SOLD_OUT', '✅ {count} items marked sold out', { count })),
      });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_MENU_BULK_UPDATE_FAILED', 'Bulk update failed'), description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  const bulkAdjustHp = async (multiplier) => {
    setBulkBusy(true);
    try {
      await mockApi.admin.bulkUpdateMenuItemHpMultiplier([...selected], multiplier);
      toast({ title: msg('FE_ADMIN_MENU_HP_MULTIPLIER_SET_TO_MULTIPLIER_FOR', '✅ HP multiplier set to {multiplier}× for {count} items', { multiplier: multiplier, count: selected.size }) });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_MENU_BULK_UPDATE_FAILED', 'Bulk update failed'), description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  // No bulk-delete endpoint — archive each selected item client-side.
  const bulkDelete = async () => {
    if (!(await confirmAction({ title: `Archive ${selected.size} selected item(s)?`, destructive: true }))) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled([...selected].map((id) => mockApi.admin.deleteMenuItem(id)));
      const ok = results.filter((r) => r.status === 'fulfilled').length;
      toast({ title: msg('FE_ADMIN_MENU_OK_ITEM_S_ARCHIVED', '✅ {ok} item(s) archived', { ok: ok }), description: results.length - ok ? `${results.length - ok} failed` : 'All done.' });
      setSelected(new Set()); await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_MENU_BULK_DELETE_FAILED', 'Bulk delete failed'), description: e.message, variant: 'destructive' }); }
    setBulkBusy(false);
  };

  const adjustHp = async (id, multiplier, name) => {
    try {
      await mockApi.admin.updateMenuItemHpMultiplier(id, { multiplier });
      const hpLabel = multiplier === 2
        ? msg('FE_ADMIN_MENU_DOUBLE', 'Double')
        : msg('FE_ADMIN_MENU_HALF', 'Half');
      toast({
        title: msg('FE_ADMIN_MENU_HP_MULTIPLIER_UPDATED', '✅ HP multiplier updated'),
        description: msg('FE_ADMIN_MENU_HP_EARNING_FOR_NAME', '{label} HP earning for "{name}".', { label: hpLabel, name }),
      });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_MENU_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  const loadCapacity = async () => { setCapacity(await mockApi.admin.getMenuCapacitySettings()); setCapacityModal(true); };
  const saveCapacity = async () => {
    try { await mockApi.admin.updateMenuCapacitySettings(capacity); toast({ title: msg('FE_ADMIN_MENU_CAPACITY_SETTINGS_SAVED', '✅ Capacity settings saved') }); setCapacityModal(false); }
    catch (e) { toast({ title: msg('FE_ADMIN_MENU_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  if (loading) return <LoadingSpinner label="Loading menu..." />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="flex gap-1 p-1 rounded-full bg-secondary">
            <span className="px-3 py-1.5 rounded-full text-xs font-bold bg-card text-primary shadow-sm">Active</span>
          </div>
          {selected.size > 0 && <span className="text-xs font-bold text-primary">{selected.size} selected</span>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {selected.size > 0 && (
            <>
              <button onClick={() => bulkToggleAvail(true)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-success text-white text-xs font-bold disabled:opacity-50"><CheckSquare className="w-3.5 h-3.5" /> Available</button>
              <button onClick={() => bulkToggleAvail(false)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-destructive text-white text-xs font-bold disabled:opacity-50"><Square className="w-3.5 h-3.5" /> Sold Out</button>
              <button onClick={() => bulkAdjustHp(2)} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Zap className="w-3.5 h-3.5" /> 2× HP</button>
              <button onClick={bulkDelete} disabled={bulkBusy} className="flex items-center gap-1 px-3 py-2 rounded-full bg-foreground text-white text-xs font-bold disabled:opacity-50"><Trash2 className="w-3.5 h-3.5" /> Delete</button>
            </>
          )}
          {(
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
          <Plus className="w-9 h-9 text-muted-foreground mx-auto mb-2" /><p className="text-sm text-muted-foreground">No menu items yet.</p>
        </div>
      ) : (
        items.map((it) => (
          <div key={it.id} className={`rounded-2xl bg-card border p-3 flex items-center gap-3 ${selected.has(it.id) ? 'border-primary/60 ring-2 ring-primary/20' : 'border-border'}`}>
            <button aria-label={`Select ${it.name}`} onClick={() => toggleSelect(it.id)} className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${selected.has(it.id) ? 'bg-primary border-primary' : 'border-input'}`}>
              {selected.has(it.id) && <CheckSquare className="w-3 h-3 text-white" />}
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-sm text-foreground">{it.name}</span>
                {it.is_featured && <Star className="w-3.5 h-3.5 text-warn fill-amber-400" />}
                {it.is_available ? <Pill tone="green">Live</Pill> : <Pill tone="red">Sold Out</Pill>}
                {it.is_secret && <Pill tone="cocoa">Secret</Pill>}
                {it.hp_multiplier === 0.5 && <Pill tone="amber">½ HP</Pill>}
                {it.hp_multiplier === 2 && <Pill tone="flame">2× HP</Pill>}
              </div>
              <div className="text-xs text-muted-foreground">{it.menu_categories?.name} · {formatNaira(it.price)} · {it.hp_earn_value} HP · Stock {it.daily_remaining}/{it.daily_limit}</div>
            </div>
            <button disabled={!isSuperAdmin && !it.campus_id} onClick={() => adjustHp(it.id, 2, it.name)} title={msg('FE_ADMIN_MENU_DOUBLE_HP_EARN', "Double HP earn")} className="p-1.5 rounded-lg hover:bg-primary/10"><Zap className="w-3.5 h-3.5 text-primary" /></button>
            {(!isSuperAdmin || adminCampusId) && <button aria-label={`Campus settings for ${it.name}`} onClick={() => openOverride(it)} className="text-xs font-bold text-primary px-2">{msg('FE_ADMIN_MENU_CAMPUS_SETTINGS', "Campus settings")}</button>}
            <Toggle label={`Availability of ${it.name}`} checked={it.is_available} onChange={() => toggleAvail(it.id)} />
            <button disabled={!isSuperAdmin && !it.campus_id} title={!isSuperAdmin && !it.campus_id ? 'Global item — super admin edits the catalogue' : undefined} aria-label={`Edit ${it.name}`} onClick={() => setModal({ item: { ...it, price: String(it.price) }, isNew: false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
            <button disabled={!isSuperAdmin && !it.campus_id} aria-label={`Archive ${it.name}`} onClick={() => remove(it.id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
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
              <Field label={msg('FE_ADMIN_MENU_DAILY_LIMIT', "Daily Limit")}><TextInput type="number" value={modal.item.daily_limit ?? ''} onChange={(e) => setModal({ item: { ...modal.item, daily_limit: e.target.value === '' ? null : Number(e.target.value) }, isNew: modal.isNew })} /></Field>
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
            <div className="flex items-center gap-2"><Toggle label={msg('FE_ADMIN_MENU_FEATURED', "Featured")} checked={!!modal.item.is_featured} onChange={(v) => setModal({ item: { ...modal.item, is_featured: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">{msg('FE_ADMIN_MENU_FEATURED', "Featured")}</span></div>
            <div className="flex items-center gap-2"><Toggle label={msg('FE_ADMIN_MENU_HIDDEN_ONLY_FOUND_BY_SEARCH', "Hidden — only found by search")} checked={!!modal.item.is_secret} onChange={(v) => setModal({ item: { ...modal.item, is_secret: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">{msg('FE_ADMIN_MENU_HIDDEN_ONLY_FOUND_BY_SEARCH', "Hidden — only found by search")}</span></div>

            {/* Per-item variations & add-ons — managed on the same screen as the item */}
            <div className="pt-2 border-t border-border">
              <MenuItemModifiers itemId={modal.isNew ? null : modal.item.id} />
            </div>

            <button onClick={save} disabled={saving} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">{modal.isNew ? 'Create Item' : 'Save Changes'}</button>
          </div>
        )}
      </Modal>

      <Modal open={capacityModal} onClose={() => setCapacityModal(false)} title="Capacity Settings">
        {capacity && (
          <div className="space-y-4">
            <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">{msg('FE_ADMIN_MENU_THREE_DISTINCT_CAPACITY_CONTROLS_CHANGES_APPLY_T', "Three distinct capacity controls. Changes apply to this campus immediately.")}</div>
            <Field label="Kitchen / Daily Capacity (total orders/day)" hint="Max orders the kitchen accepts per day. Leave blank to remove the daily cap."><TextInput type="number" value={capacity.daily_order_capacity ?? ''} onChange={(e) => setCapacity({ ...capacity, daily_order_capacity: e.target.value === '' ? null : Number(e.target.value) })} /></Field>
            <button onClick={saveCapacity} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Save Capacity Settings</button>
          </div>
        )}
      </Modal>

      <Modal open={!!override} onClose={() => setOverride(null)} title={msg('FE_ADMIN_MENU_CAMPUS_MENU_SETTINGS', "Campus Menu Settings")}>
        {override && <div className="space-y-3">
          <p className="text-sm font-bold">{override.item.name}</p>
          <p className="text-xs text-muted-foreground">{msg('FE_ADMIN_MENU_CHANGES_APPLY_TO_THIS_CAMPUS_BLANK_PRICE_AND_DAI', "Changes apply to this campus. Blank price and daily limit use the catalogue values; blank times allow all hours.")}</p>
          <div className="flex gap-2 items-center"><Toggle label={msg('FE_ADMIN_MENU_AVAILABLE_ON_THIS_CAMPUS', "Available on this campus")} checked={override.is_available} onChange={value => setOverride({ ...override, is_available: value })} /><span>{msg('FE_ADMIN_MENU_AVAILABLE', "Available")}</span></div>
          <Field label={msg('FE_ADMIN_MENU_CAMPUS_PRICE', "Campus price (₦)")}><TextInput type="number" min="0" value={override.price_override} onChange={event => setOverride({ ...override, price_override: event.target.value })} /></Field>
          <Field label={msg('FE_ADMIN_MENU_CAMPUS_DAILY_LIMIT', "Campus daily limit")}><TextInput type="number" min="0" value={override.daily_limit} onChange={event => setOverride({ ...override, daily_limit: event.target.value })} /></Field>
          <Field label={msg('FE_ADMIN_MENU_AVAILABLE_FROM_LAGOS_TIME', "Available from (Lagos time)")}><TextInput type="time" value={override.opens_at} onChange={event => setOverride({ ...override, opens_at: event.target.value })} /></Field>
          <Field label={msg('FE_ADMIN_MENU_AVAILABLE_UNTIL_LAGOS_TIME', "Available until (Lagos time)")}><TextInput type="time" value={override.closes_at} onChange={event => setOverride({ ...override, closes_at: event.target.value })} /></Field>
          <button onClick={saveOverride} disabled={overrideBusy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">{msg('FE_ADMIN_MENU_SAVE_CAMPUS_SETTINGS', "Save Campus Settings")}</button>
        </div>}
      </Modal>

      <AdminCategories open={showCats} onClose={() => setShowCats(false)} onChanged={() => { load(); mockApi.menu.getCategories().then((c) => setCategories(Array.isArray(c) ? c : (c?.categories || []))); }} />
    </div>
  );
}