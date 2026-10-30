import { msg, useMessages } from '@/lib/messages';
import type { Order } from '@/types/orders';

export default function OrderRewardSummary({ order }: { order: Order }) {
  useMessages();
  const reward = order.food_hp_reward;
  if (!reward) return null;
  const copy = reward.status === 'reserved'
    ? msg('FE_ORDER_HP_RESERVED', '{name}: {multiplier}× food HP is reserved for this order and awarded on delivery.', reward)
    : reward.status === 'applied'
      ? msg('FE_ORDER_HP_APPLIED', '{name}: {multiplier}× food HP was applied to this order.', reward)
      : reward.status === 'released'
        ? msg('FE_ORDER_HP_RELEASED', 'The HP bonus selected for this order was released. Check My Rewards for its current availability.')
        : msg('FE_ORDER_HP_UNAVAILABLE', 'Your HP reward receipt could not be loaded. Refresh this page to check its status.');
  return <section className="rounded-2xl border border-primary/20 bg-primary/5 p-4 text-left" aria-label={msg('FE_ORDER_HP_TITLE', 'Order HP reward')}>
    <h2 className="font-bold text-sm">{msg('FE_ORDER_HP_TITLE', 'Order HP reward')}</h2>
    <p className="text-sm text-muted-foreground mt-1" role={reward.status === 'unavailable' ? 'alert' : undefined}>{copy}</p>
  </section>;
}
