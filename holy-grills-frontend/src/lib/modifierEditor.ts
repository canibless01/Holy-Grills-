import { msg } from '@/lib/messages';
/** Validate the complete editor before issuing any destructive requests. */
export function parseModifierOptions(text: string) {
  const names = new Set<string>();
  return text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const separator = line.lastIndexOf(':');
    const name = (separator < 0 ? line : line.slice(0, separator)).trim();
    const priceText = separator < 0 ? '0' : line.slice(separator + 1).trim();
    const price = Number(priceText);
    if (!name || !priceText || !Number.isFinite(price) || price < 0) {
      throw new Error(msg('FE_MODIFIER_EDITOR_EACH_OPTION_NEEDS_A_NAME_AND_A_NON', 'Each option needs a name and a non-negative price, for example Chicken:200.'));
    }
    if (names.has(name.toLowerCase())) throw new Error(msg('FE_MODIFIER_EDITOR_DUPLICATE_OPTION_NAME', 'Duplicate option: {name}.', { name: name }));
    names.add(name.toLowerCase());
    return { name, price_delta: price };
  });
}

export function modifierEditorPayload(varGroups, addonGroups) {
  const requireName = group => {
    const name = group.name.trim();
    if (!name) throw new Error(msg('FE_MODIFIER_EDITOR_EVERY_MODIFIER_GROUP_NEEDS_A_NAME', 'Every modifier group needs a name.'));
    return name;
  };
  const variation_groups = varGroups.map(group => {
    const options = parseModifierOptions(group.optionsText);
    if (!options.length) throw new Error(msg('FE_MODIFIER_EDITOR_EVERY_VARIATION_GROUP_NEEDS_AT_LEAST', 'Every variation group needs at least one option.'));
    return { id: group.id, name: requireName(group), is_required: !!group.is_required, options };
  });
  const addon_groups = addonGroups.map(group => {
    const options = parseModifierOptions(group.addonsText);
    const min = Number(group.min_select), max = Number(group.max_select);
    if (!options.length || !Number.isInteger(min) || !Number.isInteger(max) || min < 0 || max < 1 || min > max || max > options.length) {
      throw new Error(msg('FE_MODIFIER_EDITOR_ADD_ON_SELECTION_LIMITS_MUST_BE_WHOLE', 'Add-on selection limits must be whole numbers: minimum 0 or more, maximum 1 or more, and no greater than the number of options.'));
    }
    return { id: group.id, name: requireName(group), is_required: min > 0, min_select: min, max_select: max,
      addons: options.map(option => ({ name: option.name, price: option.price_delta })) };
  });
  return { variation_groups, addon_groups };
}
