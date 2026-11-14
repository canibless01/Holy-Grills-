import { msg } from '@/lib/messages';
export default function CapacityGuide() {
  return <div className="rounded-xl border border-border bg-muted/40 p-3 text-xs space-y-2">
    <p><strong>{msg('FE_CAPACITY_DAILY', 'Daily kitchen slots')}</strong> — {msg('FE_CAPACITY_DAILY_HELP', 'The campus-wide limit for one delivery date, across all ordering windows.')}</p>
    <p><strong>{msg('FE_CAPACITY_ORDERING', 'Ordering-window slots')}</strong> — {msg('FE_CAPACITY_ORDERING_HELP', 'The limit for one ordering window on that date. Checkout must have room under both limits.')}</p>
    <p><strong>{msg('FE_CAPACITY_DELIVERY', 'Delivery planning target')}</strong> — {msg('FE_CAPACITY_DELIVERY_HELP', 'The delivery window groups rider runs and delivery times. Its planning value does not enforce checkout capacity.')}</p>
    <p className="text-muted-foreground">{msg('FE_CAPACITY_UNITS', 'A standard order uses one kitchen slot; a squad order uses its meal count. Menu-item daily limits separately cap units of that item.')}</p>
  </div>;
}
