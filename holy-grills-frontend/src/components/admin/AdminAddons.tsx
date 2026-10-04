import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Save, Pencil } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card } from './AdminShared';
import { toast } from '@/components/ui/use-toast';

const parseOpts = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean).map((line, i) => {
  const [name, delta = '0'] = line.split(':').map((x) => x.trim());
  return { id: `opt_${Date.now()}_${i}`, name, price_delta: Number(delta) || 0 };
});
const optsToText = (opts = []) => opts.map((o) => `${o.name}:${o.price_delta}`).join('\n');

export default function AdminAddons() {
  const [config, setConfig] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [itemId, setItemId] = useState('');
  const [varGroups, setVarGroups] = useState([]);
  const [addonGroups, setAddonGroups] = useState([]);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null); // global add-on being edited inline

  const load = async (id = itemId) => {
    let c = config;
    try { if (!c) { c = await mockApi.admin.getAddonsConfig(); setConfig(c); } }
    catch { if (!c) { c = { global_addons: [] }; setConfig(c); } }
    if (!menuItems.length) {
      try { const mi = await mockApi.admin.getMenuItems(); setMenuItems(mi || []); if (mi?.length && !id) { id = mi[0].id; setItemId(id); } } catch { /* ignore */ }
    }
    if (!id) { setVarGroups([]); setAddonGroups([]); return; }
    try {
      const [detail, addons] = await Promise.all([mockApi.menu.getItem(id), mockApi.menu.getAddons(id)]);
      setVarGroups((detail?.variation_groups || []).map((g) => ({ ...g, optionsText: optsToText(g.options || g.variations || []) })));
      setAddonGroups((addons?.addon_groups || []).map((g) => ({ ...g, addonsText: (g.addons || []).map((a) => `${a.name}:${a.price}`).join('\n') })));
    } catch { setVarGroups([]); setAddonGroups([]); }
  };
  useEffect(() => { load(); }, [itemId]);

  const reloadGlobal = async () => { try { setConfig(await mockApi.admin.getAddonsConfig()); } catch { /* ignore */ } };
  const addGlobal = () => setEditing({ name: '', price: 0 });
  const saveGlobal = async () => {
    if (!editing.name) { toast({ title: 'Name required', variant: 'destructive' }); return; }
    try {
      if (editing.id) await mockApi.admin.updateGlobalAddon(editing.id, { name: editing.name, price: Number(editing.price) || 0 });
      else await mockApi.admin.createGlobalAddon({ name: editing.name, price: Number(editing.price) || 0, group_id: null });
      toast({ title: '✅ Global addon saved' });
      setEditing(null);
      await reloadGlobal();
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
  };
  const delGlobal = async (id) => { if (!confirm('Archive this global addon?')) return; try { await mockApi.admin.deleteGlobalAddon(id); toast({ title: 'Addon archived' }); await reloadGlobal(); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } };

  const addVarGroup = () => setVarGroups((gs) => [...gs, { id: `vg_${Date.now()}`, name: '', is_required: true, optionsText: '' }]);
  const addAddonGroup = () => setAddonGroups((gs) => [...gs, { id: `ag_${Date.now()}`, name: '', is_required: false, min_select: 0, max_select: 3, addonsText: '' }]);

  const save = async () => {
    if (!itemId) return;
    setSaving(true);
    const variation_groups = varGroups.map((g) => ({ id: g.id, name: g.name, is_required: !!g.is_required, options: parseOpts(g.optionsText) }));
    const addon_groups = addonGroups.map((g) => ({ id: g.id, name: g.name, is_required: !!g.is_required, min_select: g.min_select || 0, max_select: g.max_select || 3, addons: parseOpts(g.addonsText).map((a) => ({ id: a.id, name: a.name, price: a.price_delta })) }));
    try {
      await mockApi.admin.saveItemModifiers(itemId, { variation_groups, addon_groups });
      toast({ title: '✅ Modifiers saved' });
      await load(itemId);
    } catch (e) { toast({ title: 'Save failed', description: e.message, variant: 'destructive' }); }
    setSaving(false);
  };

  if (!config) return <LoadingSpinner label="Loading addons..." />;

  return (
    <div className="space-y-5">
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
            <div key={a.id} className="rounded-xl bg-white border border-border p-3 flex items-center gap-3">
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{a.name}</div><div className="text-xs text-muted-foreground">{formatNaira(a.price)}</div></div>
              <button onClick={() => setEditing({ id: a.id, name: a.name, price: a.price })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
              <button onClick={() => delGlobal(a.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
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
            </div>
            <div className="flex gap-2">
              <button onClick={saveGlobal} className="flex-1 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold">Save</button>
              <button onClick={() => setEditing(null)} className="px-4 py-2 rounded-full bg-secondary text-foreground text-xs font-bold">Cancel</button>
            </div>
          </div>
        )}
      </div>

      {/* Per-item modifiers */}
      <div>
        <h3 className="font-bold text-sm text-foreground mb-1">Per-Item Modifiers</h3>
        <p className="text-[11px] text-muted-foreground mb-2">Variation groups (combo choices with price deltas) and add-on groups (optional extras with a min/max) scoped to a single menu item.</p>
        <select value={itemId} onChange={(e) => setItemId(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm mb-3">
          <option value="" disabled>Select a menu item</option>
          {menuItems.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>

        <div className="space-y-3">
          <div className="flex items-center justify-between"><span className="text-xs font-bold text-muted-foreground uppercase">Variation Groups</span><button onClick={addVarGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Group</button></div>
          {varGroups.map((g, gi) => (
            <Card key={g.id}>
              <div className="space-y-2">
                <Field label="Group name (e.g. Protein, Spice level)"><TextInput value={g.name} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, name: e.target.value } : x))} placeholder="e.g. Choose your protein" /></Field>
                <label className="flex items-center gap-1.5 text-xs text-foreground font-semibold"><input type="checkbox" checked={g.is_required} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, is_required: e.target.checked } : x))} /> Required (customer must pick one)</label>
                <Field label="Options (one per line)" hint="Format: OptionName:PriceDelta — delta adds to the item price. e.g. Chicken:0, Beef:200, Fish:150">
                  <textarea value={g.optionsText} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, optionsText: e.target.value } : x))} placeholder={'Chicken:0\nBeef:200\nFish:150'} rows={3} className="w-full mt-1 p-2 rounded-lg border border-border text-xs font-mono" />
                </Field>
              </div>
            </Card>
          ))}

          <div className="flex items-center justify-between"><span className="text-xs font-bold text-muted-foreground uppercase">Add-on Groups</span><button onClick={addAddonGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Group</button></div>
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
              </div>
            </Card>
          ))}
        </div>

        <button onClick={save} disabled={saving || !itemId} className="mt-4 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"><Save className="w-4 h-4" /> Save Modifiers</button>
      </div>
    </div>
  );
}