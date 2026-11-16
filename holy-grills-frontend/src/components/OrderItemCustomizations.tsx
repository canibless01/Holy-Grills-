type TicketItem = {
  quantity?: number;
  selected_variations?: { option_id?: string; option_name?: string }[];
  order_addon_selections?: { addon_id?: string; name_snapshot?: string; quantity?: number }[];
  options_snapshot?: { notes?: string };
};

/** Saved choices describe what was bought even after the menu is edited. */
export default function OrderItemCustomizations({ item }: { item: TicketItem }) {
  const variations = Array.isArray(item.selected_variations) ? item.selected_variations : [];
  const sides = Array.isArray(item.order_addon_selections) ? item.order_addon_selections : [];
  const notes = typeof item.options_snapshot?.notes === 'string' ? item.options_snapshot.notes : '';
  if (!variations.length && !sides.length && !notes) return null;
  return (
    <div className="mt-0.5 space-y-0.5 text-xs text-muted-foreground">
      {variations.filter(v => v.option_name).map((v, i) => <p key={v.option_id || i}>{v.option_name}</p>)}
      {sides.filter(s => s.name_snapshot).map((s, i) => (
        <p key={`${s.addon_id || i}-${i}`}>{(Number(item.quantity) || 1) * (Number(s.quantity) || 1)}× {s.name_snapshot}</p>
      ))}
      {notes && <p className="whitespace-pre-wrap break-words">{notes}</p>}
    </div>
  );
}
