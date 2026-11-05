import { useState, useEffect } from 'react';
import { Plus, Trash2, Save } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { Field, TextInput } from './AdminShared';
import { msg, useMessages } from '@/lib/messages';
import { modifierEditorPayload } from '@/lib/modifierEditor';

// Per-item variations & add-ons editor, embedded inside the menu item modal.
// Two distinct modifier kinds, each fully CRUD via the live per-item endpoints:
//   • Variation groups — combo choices that add a price delta (e.g. "Choose your
//     protein: Chicken +0, Beef +200"). Required or optional, one pick per group.
//   • Add-on groups — optional extras with a min/max selection count (e.g.
//     "Choose up to 3 sides"). Each add-on has its own flat ₦ price.
// For unsaved (new) items we show a "save first" note — modifiers need an item id.

const optsToText = (opts = []) => opts.map((o) => `${o.name}:${o.price_delta}`).join('\n');

export default function MenuItemModifiers({ itemId }) {
  useMessages();
  const [varGroups, setVarGroups] = useState([]);
  const [addonGroups, setAddonGroups] = useState([]);
  const [loading, setLoading] = useState(!!itemId);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const loadModifiers = async () => {
    const [detail, addons] = await Promise.all([mockApi.menu.getItem(itemId), mockApi.menu.getAddons(itemId)]);
    setVarGroups((detail?.variation_groups || []).map(g => ({ ...g, optionsText: optsToText(g.options || []) })));
    setAddonGroups((addons?.addon_groups || []).map(g => ({ ...g, addonsText: (g.addons || []).map(a => `${a.name}:${a.price}`).join('\n') })));
  };

  useEffect(() => {
    if (!itemId) { setVarGroups([]); setAddonGroups([]); return; }
    let alive = true;
    const load = async () => {
      setLoading(true); setLoadError(false);
      try {
        const [detail, addons] = await Promise.all([mockApi.menu.getItem(itemId), mockApi.menu.getAddons(itemId)]);
        if (!alive) return;
        setVarGroups((detail?.variation_groups || []).map((g) => ({ ...g, optionsText: optsToText(g.options || g.variations || []) })));
        setAddonGroups((addons?.addon_groups || []).map((g) => ({ ...g, addonsText: (g.addons || []).map((a) => `${a.name}:${a.price}`).join('\n') })));
      } catch { if (alive) setLoadError(true); }
      if (alive) setLoading(false);
    };
    load();
    return () => { alive = false; };
  }, [itemId]);

  if (!itemId) {
    return (
      <div className="rounded-xl bg-muted border border-dashed border-border p-3 text-xs text-muted-foreground text-center">
        Save the item first to add its variations &amp; add-ons from this same screen.
      </div>
    );
  }
  if (loadError) return <div role="alert" className="text-sm text-destructive">{msg('FE_MENU_ITEM_MODIFIERS_MODIFIERS_COULD_NOT_BE_LOADED_CLOSE_AND_REOPEN_T', "Modifiers could not be loaded. Close and reopen this item to retry.")}</div>;
  if (loading) return <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">Loading modifiers…</div>;

  const addVarGroup = () => setVarGroups((gs) => [...gs, { id: `vg_${Date.now()}`, name: '', is_required: true, optionsText: '' }]);
  const addAddonGroup = () => setAddonGroups((gs) => [...gs, { id: `ag_${Date.now()}`, name: '', is_required: false, min_select: 0, max_select: 3, addonsText: '' }]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = modifierEditorPayload(varGroups, addonGroups);
      await mockApi.admin.saveItemModifiers(itemId, payload);
      await loadModifiers();
      toast({ title: msg('FE_MENU_ITEM_MODIFIERS_MODIFIERS_SAVED', '✅ Modifiers saved') });
    } catch (e) { toast({ title: msg('FE_MENU_ITEM_MODIFIERS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' }); }
    setSaving(false);
  };

  return (
    <div className="rounded-2xl border border-border p-3 space-y-3 bg-muted/40">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Variations &amp; Add-ons</span>
      </div>

      {/* Variation groups */}
      <div className="flex items-center justify-between"><span className="text-[11px] font-bold text-muted-foreground uppercase">{msg('FE_MENU_ITEM_MODIFIERS_VARIATION_GROUPS', "Variation Groups")}</span><button aria-label={msg('FE_MENU_ITEM_MODIFIERS_ADD_VARIATION_GROUP', "Add variation group")} onClick={addVarGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> {msg('FE_MENU_ITEM_MODIFIERS_GROUP', "Group")}</button></div>
      <p className="text-[11px] text-muted-foreground -mt-1">Combo choices that change the base price (e.g. "Choose your protein"). Each option adds its price delta to the item price.</p>
      {varGroups.map((g, gi) => (
        <div key={g.id} className="rounded-xl bg-card border border-border p-2.5 space-y-2">
          <Field label="Group name (e.g. Spice level, Protein)">
            <TextInput value={g.name} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, name: e.target.value } : x))} placeholder="e.g. Choose your protein" />
          </Field>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-foreground font-semibold">
              <input type="checkbox" checked={g.is_required} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, is_required: e.target.checked } : x))} />
              Required (customer must pick one)
            </label>
            <div className="ml-auto">
              <button aria-label={`Remove variation group ${g.name || gi + 1}`} onClick={() => setVarGroups((gs) => gs.filter((_, i) => i !== gi))} className="p-1.5 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
            </div>
          </div>
          <Field label="Options (one per line)" hint="Format: OptionName:PriceDelta — the delta is added to the item price. e.g. Chicken:0, Beef:200, Fish:150">
            <textarea value={g.optionsText} onChange={(e) => setVarGroups((gs) => gs.map((x, i) => i === gi ? { ...x, optionsText: e.target.value } : x))} placeholder={'Chicken:0\nBeef:200\nFish:150'} rows={3} className="w-full mt-1 p-2 rounded-lg border border-border text-xs font-mono" />
          </Field>
        </div>
      ))}

      {/* Addon groups */}
      <div className="flex items-center justify-between pt-1"><span className="text-[11px] font-bold text-muted-foreground uppercase">{msg('FE_MENU_ITEM_MODIFIERS_ADD_ON_GROUPS', "Add-on Groups")}</span><button aria-label={msg('FE_MENU_ITEM_MODIFIERS_ADD_ADD_ON_GROUP', "Add add-on group")} onClick={addAddonGroup} className="text-xs font-bold text-primary flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> {msg('FE_MENU_ITEM_MODIFIERS_GROUP', "Group")}</button></div>
      <p className="text-[11px] text-muted-foreground -mt-1">Optional extras with a selection range (e.g. "Choose up to 3 sides"). Each add-on has its own flat price.</p>
      {addonGroups.map((g, gi) => (
        <div key={g.id} className="rounded-xl bg-card border border-border p-2.5 space-y-2">
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <Field label="Group name (e.g. Extras, Sides)">
                <TextInput value={g.name} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, name: e.target.value } : x))} placeholder="e.g. Choose your sides" />
              </Field>
            </div>
            <button aria-label={`Remove add-on group ${g.name || gi + 1}`} onClick={() => setAddonGroups((gs) => gs.filter((_, i) => i !== gi))} className="p-1.5 rounded-lg hover:tone-error mt-6"><Trash2 className="w-4 h-4 text-destructive" /></button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Min selections" hint="Fewest add-ons a customer must pick (0 = optional)">
              <TextInput type="number" value={g.min_select} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, min_select: Number(e.target.value) } : x))} />
            </Field>
            <Field label="Max selections" hint="Most add-ons a customer may pick">
              <TextInput type="number" value={g.max_select} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, max_select: Number(e.target.value) } : x))} />
            </Field>
          </div>
          <Field label="Add-on options (one per line)" hint="Format: AddonName:Price — flat ₦ price for that add-on. e.g. Extra Cheese:200, Bacon:400, Coleslaw:150">
            <textarea value={g.addonsText} onChange={(e) => setAddonGroups((gs) => gs.map((x, i) => i === gi ? { ...x, addonsText: e.target.value } : x))} placeholder={'Extra Cheese:200\nBacon:400\nColeslaw:150'} rows={3} className="w-full mt-1 p-2 rounded-lg border border-border text-xs font-mono" />
          </Field>
        </div>
      ))}

      <button onClick={save} disabled={saving} className="w-full py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold flex items-center justify-center gap-2 disabled:opacity-50"><Save className="w-4 h-4" /> {saving ? 'Saving…' : 'Save Modifiers'}</button>
    </div>
  );
}