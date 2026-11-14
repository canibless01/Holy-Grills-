import { parseModifierOptions, modifierCushion } from '@/lib/modifierEditor';

export default function ModifierCushions({ group, kind, onChange }) {
  let options = [];
  try { options = parseModifierOptions(kind === 'variation' ? group.optionsText : group.addonsText); } catch { return null; }
  if (!options.length) return null;
  return <fieldset className="rounded-xl border border-border bg-muted/40 p-3 space-y-2">
    <legend className="px-1 text-xs font-bold">Delivery cushion included in each option (₦)</legend>
    <p className="text-xs text-muted-foreground">Internal allocation only. Does not increase the customer’s price.</p>
    {options.map(option => <label key={option.name} className="flex items-center justify-between gap-3 text-xs">
      <span className="min-w-0 break-words">{option.name}</span>
      <input aria-label={`Cushion for ${option.name}`} type="number" min="0" max={option.price_delta} step="0.01" className="w-28 rounded-lg border border-border bg-card p-2" value={modifierCushion(group, option.name, kind)} onChange={event => onChange({ ...group, cushionAmounts: { ...group.cushionAmounts, [option.name]: event.target.value } })} />
    </label>)}
  </fieldset>;
}
