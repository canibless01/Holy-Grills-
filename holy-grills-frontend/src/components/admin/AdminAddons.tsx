import ModifierCushions from './ModifierCushions';
import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect, useRef } from 'react';
import { Plus, Trash2, Save, Pencil } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Field, TextInput, Card } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg, useMessages } from '@/lib/messages';
import { modifierEditorPayload } from '@/lib/modifierEditor';

const optsToText = (opts = []) => opts.map((o) => `${o.name}:${o.price_delta}`).join('\n');

export default function AdminAddons() {
  useMessages();
  const [config, setConfig] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [itemId, setItemId] = useState('');
  const [varGroups, setVarGroups] = useState([]);
  const [addonGroups, setAddonGroups] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [editing, setEditing] = useState(null); // global add-on being edited inline

  const generation = useRef(0);
  const [initialError, setInitialError] = useState(false);
  const [globalError, setGlobalError] = useState(false);
  const [globalBusy, setGlobalBusy] = useState(false);
  const globalWrite = useRef(false);
  const modifierWrite = useRef(false);
  const [loadedItem, setLoadedItem] = useState('');
  const [reading, setReading] = useState(false);

  const bootstrap = async () => {
    setInitialError(false);
    try {
      const [c, mi] = await Promise.all([mockApi.admin.getAddonsConfig(), mockApi.admin.getMenuItems()]);
      setConfig(c); setMenuItems(mi || []);
      setItemId(current => current || mi?.[0]?.id || '');
    } catch { setInitialError(true); }
  };
  useEffect(() => { void bootstrap(); }, []);

  const load = async (id: string) => {
    const request = ++generation.current;
    setLoadedItem(''); setReading(true); setLoadError(false);
    if (!id) { setVarGroups([]); setAddonGroups([]); setReading(false); return; }
    try {
      const [detail, addons] = await Promise.all([mockApi.menu.getItem(id), mockApi.menu.getAddons(id)]);
      if (request !== generation.current) return;
      setVarGroups((detail?.variation_groups || []).map((g) => ({ ...g, optionsText: optsToText(g.options || g.variations || []) })));
      setAddonGroups((addons?.addon_groups || []).map((g) => ({ ...g, addonsText: (g.addons || []).map((a) => `${a.name}:${a.price}`).join('\n') })));
      setLoadedItem(id);
    } catch { if (request === generation.current) setLoadError(true); }
    finally { if (request === generation.current) setReading(false); }
  };
  useEffect(() => { void load(itemId); return () => { generation.current += 1; }; }, [itemId]);

  const reloadGlobal = async () => {
    setGlobalError(false);
    try { setConfig(await mockApi.admin.getAddonsConfig()); }
    catch { setGlobalError(true); }
  };
  const addGlobal = () => setEditing({ name: '', price: 0, cushion_amount: 0 });
  const saveGlobal = async () => {
    if (globalWrite.current || !editing) return;
    if (!editing.name.trim()) { toast({ title: msg('FE_ADMIN_ADDONS_NAME_REQUIRED', 'Name required'), variant: 'destructive' }); return; }
    globalWrite.current = true; setGlobalBusy(true);
    try {
      if (editing.id) await mockApi.admin.updateGlobalAddon(editing.id, { name: editing.name, price: Number(editing.price), cushion_amount: Number(editing.cushion_amount) });
      else await mockApi.admin.createGlobalAddon({ name: editing.name, price: Number(editing.price), cushion_amount: Number(editing.cushion_amount), group_id: null });
      toast({ title: msg('FE_ADMIN_ADDONS_GLOBAL_ADDON_SAVED', '✅ Global addon saved') });
      setEditing(null);
      await reloadGlobal();
    } catch (e) { toast({ title: msg('FE_ADMIN_ADDONS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' }); }
    finally { globalWrite.current = false; setGlobalBusy(false); }
  };
  const delGlobal = async (id) => { if (!(await confirmAction({ title: "Archive this global addon?", destructive: true, confirmLabel: "Archive" }))) return; try { await mockApi.admin.deleteGlobalAddon(id); toast({ title: msg('FE_ADMIN_ADDONS_ADDON_ARCHIVED', 'Addon archived') }); await reloadGlobal(); } catch (e) { toast({ title: msg('FE_ADMIN_ADDONS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); } };

  const addVarGroup = () => setVarGroups((gs) => [...gs, { id: `vg_${Date.now()}`, name: '', is_required: true, optionsText: '' }]);
  const addAddonGroup = () => setAddonGroups((gs) => [...gs, { id: `ag_${Date.now()}`, name: '', is_required: false, min_select: 0, max_select: 3, addonsText: '' }]);

  const save = async () => {
    if (modifierWrite.current || !itemId || loadError || reading || loadedItem !== itemId) return;
    modifierWrite.current = true;
    setSaving(true);
    try {
      const payload = modifierEditorPayload(varGroups, addonGroups);
      await mockApi.admin.saveItemModifiers(itemId, payload);
      toast({ title: msg('FE_ADMIN_ADDONS_MODIFIERS_SAVED', '✅ Modifiers saved') });
      await load(itemId);
    } catch (e) { toast({ title: msg('FE_ADMIN_ADDONS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' }); }
    modifierWrite.current = false; setSaving(false);
  };

  if (initialError) return <div role="alert"><p>{msg('FE_ADMIN_ADDONS_READ_FAILED', 'Add-ons could not be loaded. Retry before editing.')}</p><button onClick={bootstrap}>{msg('FE_LOOKUP_RETRY', 'Retry')}</button></div>;
  if (!config) return <StaffPanelSkeleton />;

  return (
    <div className="space-y-5">
      {globalError && <div role="alert"><p>{msg('FE_ADMIN_ADDONS_REFRESH_FAILED', 'The saved add-on list could not be refreshed.')}</p><button onClick={reloadGlobal}>{msg('FE_LOOKUP_RETRY', 'Retry')}</button></div>}
      <fieldset disabled={globalBusy} className="min-w-0">
      {/* Global add-ons — independent items customers can add to any order. */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="font-bold text-sm text-foreground">Global Add-ons</h3>
            <p className="text-[11px] text-muted-foreground">Standalone extras customers can add to any order (not scoped to a single menu item).</p>
          </div>
          <button onClick={addGlobal} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-3.5 h-3.5" /> Add Global</button>
        </div>
        <div className="space-y-2">
          {config.global_addons.map((a) => (
            <div key={a.id} className="rounded-xl bg-card border border-border p-3 flex items-center gap-3">
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{a.name}</div><div className="text-xs text-muted-foreground">{formatNaira(a.price)}</div></div>
              <button onClick={() => setEditing({ id: a.id, name: a.name, price: a.price, cushion_amount: a.cushion_amount ?? 0 })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
              <button onClick={() => delGlobal(a.id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
            </div>
          ))}
          {config.global_addons.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No global add-ons yet.</p>}
        </div>
        {editing && (
          <div className="rounded-xl bg-muted border border-border p-3 space-y-2 mt-2">
            <div className="text-xs font-bold text-foreground uppercase">{editing.id ? 'Edit global add-on' : 'New global add-on'}</div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Name"><TextInput value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="e.g. Extra sauce" /></Field>
              <Field label="Price (₦)"><TextInput type="number" value={editing.price} onChange={(e) => setEditing({ ...editing, price: e.target.value })} /></Field>
              <Field label="Delivery cushion included (₦)" hint="Part of the selling price, not an extra charge."><TextInput type="number" min="0" max={editing.price} step="0.01" value={editing.cushion_amount} onChange={e => setEditing({ ...editing, cushion_amount: e.target.value })} /></Field>
            </div>
            <div className="flex gap-2">
              <button onClick={saveGlobal} className="flex-1 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold">Save</button>
              <button onClick={() => setEditing(null)} className="px-4 py-2 rounded-full bg-secondary text-foreground text-xs font-bold">Cancel</button>
            </div>
          </div>
        )}
      </div>

      </fieldset>
      {/* Per-item modifiers */}
      <div>
        <h3 className="font-bold text-sm text-foreground mb-1">Per-Item Modifiers</h3>
        <p className="text-[11px] text-muted-foreground mb-2">Variation groups (combo choices with price deltas) and add-on groups (optional extras with a min/max) scoped to a single menu item.</p>
        <select aria-label={msg('FE_ADMIN_ADDONS_MENU_ITEM_FOR_MODIFIERS', "Menu item for modifiers")} disabled={saving} value={itemId} onChange={(e) => setItemId(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm mb-3">
          <option value="" disabled>Select a menu item</option>
          {menuItems.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>

        {loadError && <p role="alert" className="text-sm text-destructive">{msg('FE_ADMIN_ADDONS_MODIFIERS_COULD_NOT_BE_LOADED_SELECT_THE_ITEM_AG', "Modifiers could not be loaded. Select the item again before saving.")}</p>}
        {loadError && <button onClick={() => load(itemId)}>{msg('FE_LOOKUP_RETRY', 'Retry')}</button>}
        {reading && <p role="status">{msg('FE_ADMIN_ADDONS_READING', 'Loading modifiers…')}</p>}
        <fieldset disabled={saving || reading || loadError || loadedItem !== itemId} className="space-y-3 min-w-0">
          <div className="flex items-center justify-between"><span className="text-xs font-bold text-muted-foreground uppercase">{msg('FE_ADMIN_ADDONS_VARIATION_GROUPS', "Variation Groups")}</span><button aria-label={msg('FE_ADMIN_ADDONS_ADD_VARIATION_GROUP', "Add variation group")} onClick={addVarGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> {msg('FE_ADMIN_ADDONS_GROUP', "Group")}</button></div>
          {varGroups.map((g, gi) => (
            <Card key={g.id}>
              <div className="space-y-2">
                <Field label="Group name (e.g. Protein, Spice level)"><TextInput value={g.name} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, name: e.target.value } : x))} placeholder="e.g. Choose your protein" /></Field>
                <label className="flex items-center gap-1.5 text-xs text-foreground font-semibold"><input type="checkbox" checked={g.is_required} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, is_required: e.target.checked } : x))} /> Required (customer must pick one)</label>
                <Field label="Options (one per line)" hint="Format: OptionName:PriceDelta — delta adds to the item price. e.g. Chicken:0, Beef:200, Fish:150">
                  <textarea value={g.optionsText} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, optionsText: e.target.value } : x))} placeholder={'Chicken:0\nBeef:200\nFish:150'} rows={3} className="w-full mt-1 p-2 rounded-lg border border-border text-xs font-mono" />
                </Field>
                <ModifierCushions group={g} kind="variation" onChange={next => setVarGroups(gs => gs.map((x, i) => i === gi ? next : x))} />
                <button aria-label={`Remove variation group ${g.name || gi + 1}`} onClick={() => setVarGroups(gs => gs.filter((_, i) => i !== gi))} className="text-xs text-destructive">{msg('FE_ADMIN_ADDONS_REMOVE_GROUP', "Remove group")}</button>
              </div>
            </Card>
          ))}

          <div className="flex items-center justify-between"><span className="text-xs font-bold text-muted-foreground uppercase">{msg('FE_ADMIN_ADDONS_ADD_ON_GROUPS', "Add-on Groups")}</span><button aria-label={msg('FE_ADMIN_ADDONS_ADD_ADD_ON_GROUP', "Add add-on group")} onClick={addAddonGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> {msg('FE_ADMIN_ADDONS_GROUP', "Group")}</button></div>
          {addonGroups.map((g, gi) => (
            <Card key={g.id}>
              <div className="space-y-2">
                <Field label="Group name (e.g. Sides, Extras)"><TextInput value={g.name} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, name: e.target.value } : x))} placeholder="e.g. Choose your sides" /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Min selections" hint="Fewest a customer must pick (0 = optional)"><TextInput type="number" value={g.min_select} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, min_select: Number(e.target.value) } : x))} /></Field>
                  <Field label="Max selections" hint="Most a customer may pick"><TextInput type="number" value={g.max_select} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, max_select: Number(e.target.value) } : x))} /></Field>
                </div>
                <Field label="Add-on options (one per line)" hint="Format: AddonName:Price — flat ₦ price. e.g. Extra Cheese:200, Bacon:400, Coleslaw:150">
                  <textarea value={g.addonsText} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, addonsText: e.target.value } : x))} placeholder={'Extra Cheese:200\nBacon:400\nColeslaw:150'} rows={3} className="w-full mt-1 p-2 rounded-lg border border-border text-xs font-mono" />
                </Field>
                <ModifierCushions group={g} kind="addon" onChange={next => setAddonGroups(gs => gs.map((x, i) => i === gi ? next : x))} />
                <button aria-label={`Remove add-on group ${g.name || gi + 1}`} onClick={() => setAddonGroups(gs => gs.filter((_, i) => i !== gi))} className="text-xs text-destructive">{msg('FE_ADMIN_ADDONS_REMOVE_GROUP', "Remove group")}</button>
              </div>
            </Card>
          ))}
        </fieldset>

        <button onClick={save} disabled={saving || reading || loadError || !itemId || loadedItem !== itemId} className="mt-4 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"><Save className="w-4 h-4" /> {msg('FE_ADMIN_ADDONS_SAVE_MODIFIERS', "Save Modifiers")}</button>
      </div>
    </div>
  );
}
