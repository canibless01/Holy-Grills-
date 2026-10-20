import OrderRewardSummary from '@/components/OrderRewardSummary';
import OrderPaymentActions from '@/components/OrderPaymentActions';
import OrderItemCustomizations from '@/components/OrderItemCustomizations';
import { msg, useMessages } from '@/lib/messages';
import { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Check, Flame, Package, MapPin, CreditCard, Users, Share2, Clock } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { playSound } from '@/lib/soundManager';
import { formatNaira, formatDateTime, ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import { triggerMascotCelebration } from '@/lib/mascots';
import MascotStandee from '@/components/mascot/MascotStandee';
import FlameMark from '@/components/FlameMark';
import ShareSheet from '@/components/ShareSheet';

// "18:00" → "6:00 PM"
const to12h = (t) => {
  if (!t) return '';
  const [h, m] = t.split(':').map(Number);
  if (Number.isNaN(h)) return t;
  return `${h % 12 || 12}:${String(m ?? 0).padStart(2, '0')} ${h >= 12 ? 'PM' : 'AM'}`;
};

export default function OrderConfirmation() {
  useMessages();
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { getSetting } = useHolyGrill();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [shareOpen, setShareOpen] = useState(false);
  const claimToken = location.state?.claim_token || (() => {
    try { return JSON.parse(localStorage.getItem('hg_guest_orders') || '[]').find(saved => saved.id === id)?.claim_token; }
    catch { return undefined; }
  })();
  // "Today is full" reschedule — the order landed on the next available day.
  const isScheduled = order?.is_scheduled || location.state?.is_scheduled;
  const scheduledFor = order?.scheduled_for || location.state?.scheduled_for;
  const winStart = order?.delivery_window_start || location.state?.delivery_window_start;
  const winEnd = order?.delivery_window_end || location.state?.delivery_window_end;
  const closed = ['cancelled', 'refunded'].includes(order?.status);
  const paid = order?.payment_status === 'paid' || order?.payment_status === 'partially_refunded';
  const reloadOrder = async () => setOrder(await mockApi.orders.get(id, claimToken ? { claim_token: claimToken } : {}));
  const giftItemName = getSetting('first_order_gift_item_name', 'Hot Dog');

  useEffect(() => {
    const load = async () => {
      try {
        if (id && id !== 'pending') {
          const o = await mockApi.orders.get(id, claimToken ? { claim_token: claimToken } : {});
          setOrder(o);
          if (o?.payment_status === 'paid') playSound('order_placed');
          if (o?.hp_earned > 0) setTimeout(() => playSound('hp_earned'), 700);
          if (o?.payment_status === 'paid') setTimeout(() => triggerMascotCelebration('cheering'), 900);
        }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, [id, claimToken]);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in text-center py-8">
        <div className="w-24 h-24 rounded-full bg-muted mx-auto animate-pulse" />
        <div className="h-7 w-48 bg-muted rounded mx-auto animate-pulse" />
        <div className="h-32 bg-muted rounded-2xl animate-pulse" />
        <div className="h-48 bg-muted rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="text-center py-16 space-y-4">
        <MascotStandee mascot="worried" className="w-32 h-32 mx-auto" alt="Order not found" />
        <p className="text-sm text-muted-foreground">Order not found</p>
        <button onClick={() => navigate('/')} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold">Back to Home</button>
      </div>
    );
  }

  // Progress fill follows the real kitchen/delivery pipeline instead of a
  // hardcoded 15% — the bar now means something on every status.
  const STATUS_STEPS = ['received', 'preparing', 'ready', 'out_for_delivery', 'delivered'];
  const progressPct = (() => {
    const idx = STATUS_STEPS.indexOf(order.status);
    if (order.status === 'delivered') return 100;
    if (idx < 0) return 15;
    return Math.round(((idx + 1) / STATUS_STEPS.length) * 100);
  })();

  return (
    <div className="space-y-5 animate-fade-in text-center max-w-md mx-auto">
      {/* Success hero — the one gradient bed on this page, with the flame
          watermark; everything below stays on warm cards. */}
      <motion.div
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 18 }}
        className="relative overflow-hidden rounded-3xl bg-gradient-cta pt-8 pb-6 px-4 text-white shadow-glow -mx-4 sm:mx-0"
      >
        <FlameMark className="absolute -right-6 -top-6 w-28 h-28 opacity-15 pointer-events-none" />
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.1 }}
          className="relative inline-block"
        >
          <div className={`w-24 h-24 rounded-full ${paid ? 'bg-white/25' : 'bg-white/15'} flex items-center justify-center mx-auto backdrop-blur-[2px]`}>
            <div className="w-16 h-16 rounded-full bg-white flex items-center justify-center">
              {paid ? <Check className="w-8 h-8 text-primary" strokeWidth={3} /> : <CreditCard className="w-8 h-8 text-primary" />}
            </div>
          </div>
        </motion.div>
        <h1 className="font-heading font-extrabold text-2xl mt-4 relative">{closed ? msg('FE_CONFIRMATION_CLOSED_TITLE', 'Order closed') : !paid ? msg('FE_CONFIRMATION_PAYMENT_TITLE', 'Order saved — payment required') : isScheduled ? msg('FE_CONFIRMATION_SCHEDULED_TITLE', 'Order Scheduled!') : msg('FE_CONFIRMATION_CONFIRMED_TITLE', 'Order Confirmed!')}</h1>
        <p className="text-sm text-white/85 mt-1 relative">
          {closed ? msg('FE_CONFIRMATION_CLOSED_BODY', 'This order is no longer awaiting payment or fulfilment.') : !paid ? msg('FE_CONFIRMATION_AWAITING_PAYMENT', 'Your order is awaiting payment.') : isScheduled
            ? msg('FE_CONFIRMATION_SCHEDULED_BODY', "You're scheduled for {date}{window}.", {
                date: scheduledFor ? new Date(scheduledFor).toLocaleDateString('en-NG', { timeZone: 'Africa/Lagos', weekday: 'long', month: 'long', day: 'numeric' }) : msg('FE_CONFIRMATION_NEXT_DAY', 'the next available day'),
                window: winStart ? msg('FE_CONFIRMATION_DELIVERY_WINDOW', ', delivery between {start}–{end}', { start: to12h(winStart), end: to12h(winEnd) }) : '',
              })
            : order.payment_status !== 'paid' ? msg('FE_CONFIRMATION_AWAITING_PAYMENT', 'Your order is awaiting payment.')
            : order.status === 'preparing' ? msg('FE_CONFIRMATION_PREPARING', 'Your flame grilled order is being prepared.') : msg('FE_CONFIRMATION_RECEIVED', 'Your order has been received by the kitchen.')}
        </p>
        <div className="inline-block mt-3 px-4 py-1.5 rounded-full bg-white/20 border border-white/30 text-xs font-bold">
          Order #{(order.order_number || order.id || '').toUpperCase()}
        </div>
      </motion.div>

      <OrderRewardSummary order={order} />
      <OrderPaymentActions order={order} claimToken={claimToken} onUpdated={reloadOrder} autoStart={!!location.state?.startPayment} initialError={location.state?.paymentError || ''} />

      {/* HP Earned */}
      {order.hp_earned > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-2xl bg-gradient-gold border border-primary/30 p-4"
        >
          <div className="flex items-center justify-center gap-2">
            <Flame className="w-6 h-6 text-primary" />
            <span className="font-heading font-extrabold text-2xl text-primary">+{order.hp_earned} HP</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">Holy Points earned from this order!</p>
          {order.order_items?.some((it) => it.hp_multiplier && it.hp_multiplier !== 1) && (
            <div className="mt-3 pt-3 border-t border-primary/30 space-y-1 text-left">
              {order.order_items.filter((it) => it.hp_multiplier && it.hp_multiplier !== 1).map((it, i) => (
                <div key={i} className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{it.quantity}× {it.name_snapshot}</span>
                  <span className="font-semibold">
                    {it.hp_earn_value || it.hp_earn_snapshot || 0} HP × {it.hp_multiplier} = <span className="text-primary font-bold">{Math.round((it.hp_earn_value || it.hp_earn_snapshot || 0) * it.hp_multiplier * it.quantity)} HP</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* First-order gift */}
      {paid && order.is_first_order && giftItemName && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="rounded-2xl bg-accent/20 border border-accent/40 p-4 text-center"
        >
          <div className="text-3xl mb-1">🎁</div>
          <h3 className="font-bold text-sm text-accent-foreground">First Order Gift!</h3>
          <p className="text-xs text-accent-foreground mt-1">Enjoy a free {giftItemName} on us. Welcome to Holy Grills! 🔥</p>
        </motion.div>
      )}

      {/* Order Summary */}
      <div className="text-left rounded-2xl bg-card border border-border p-4 space-y-3 shadow-card">
        <h3 className="font-bold text-sm text-foreground">Order Summary</h3>
        <div className="space-y-2">
          {(order.order_items || []).map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <div><span className="text-muted-foreground">{item.quantity}× {item.name_snapshot}</span><OrderItemCustomizations item={item} /></div>
              <span className="font-semibold text-foreground">{formatNaira(item.line_total)}</span>
            </div>
          ))}
        </div>
        <div className="border-t border-border pt-2 space-y-1">
          {order.discount_amount > 0 && (
            <div className="flex justify-between text-xs text-success">
              <span>Discount</span>
              <span>-{formatNaira(order.discount_amount)}</span>
            </div>
          )}
          <div className="flex justify-between font-bold">
            <span className="text-foreground">{order.payment_status === 'paid' ? msg('FE_CONFIRMATION_TOTAL_PAID', 'Total Paid') : msg('FE_CONFIRMATION_ORDER_TOTAL', 'Order Total')}</span>
            <span className="text-foreground">{formatNaira(order.total_amount)}</span>
          </div>
        </div>
      </div>

      {/* Order Details */}
      <div className="text-left rounded-2xl bg-card border border-border p-4 space-y-3 shadow-card">
        <div className="flex items-center gap-3 text-sm">
          <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Placed at</div>
            <div className="font-semibold text-foreground">{formatDateTime(order.created_at)}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <MapPin className="w-4 h-4 text-muted-foreground shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Delivery to</div>
            <div className="font-semibold text-foreground">{order.delivery_address?.line1 || msg('FE_ORDER_ADDRESS_UNAVAILABLE', 'Delivery details unavailable')}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Package className="w-4 h-4 text-muted-foreground shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Window</div>
            <div className="font-semibold text-foreground">{order.delivery_window?.label || (winStart && winEnd ? `${to12h(winStart)}–${to12h(winEnd)}` : msg('FE_ORDER_WINDOW_PENDING', 'Delivery window will be assigned'))}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <CreditCard className="w-4 h-4 text-muted-foreground shrink-0" />
          <div>
            <div className="text-xs text-muted-foreground">Payment</div>
            <div className="font-semibold text-foreground capitalize">
              {order.wallet_amount_used > 0 && order.card_amount_used > 0 ? 'Split' : order.wallet_amount_used > 0 ? 'Wallet' : 'Card'}
              {' · '}
              <span className={order.payment_status === 'paid' ? 'text-success' : 'text-accent'}>
                {order.payment_status}
              </span>
            </div>
          </div>
        </div>
        {order.is_squad_order && (
          <div className="flex items-center gap-3 text-sm">
            <Users className="w-4 h-4 text-muted-foreground shrink-0" />
            <div>
              <div className="text-xs text-muted-foreground">Squad</div>
              <div className="font-semibold text-foreground">{order.squad_name || 'Squad order'}</div>
            </div>
          </div>
        )}
      </div>

      {/* Status Timeline */}
      <div className="text-left rounded-2xl bg-card border border-border p-4 shadow-card">
        <h3 className="font-bold text-sm text-foreground mb-3">Order Status</h3>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full bg-gradient-cta transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <span className="text-xs font-bold text-primary">{ORDER_STATUS_LABELS[order.status] || order.status}</span>
        </div>
      </div>

      {/* Actions — Track Order is the next action, so it wears the hero CTA */}
      <div className="space-y-2">
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={() => navigate(`/orders/${order.id}${claimToken ? `?claim_token=${claimToken}` : ''}`)}
          className="w-full py-4 rounded-xl bg-gradient-cta text-white font-bold shadow-glow"
        >
          Track Order
        </motion.button>
        <div className="flex gap-2">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex-1 py-3 rounded-xl bg-card border border-border text-foreground font-bold text-sm hover:border-primary/30 transition-colors"
          >
            Go to Dashboard
          </button>
          {paid && <button
            onClick={() => setShareOpen(true)}
            className="flex-1 py-3 rounded-xl bg-card border border-border text-foreground font-bold text-sm flex items-center justify-center gap-1.5 hover:border-primary/30 transition-colors"
          >
            <Share2 className="w-4 h-4" />
            Share
          </button>}
        </div>
      </div>

      <ShareSheet
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        type="order"
        templateKey="order_share"
        payload={{
          orderId: order.id,
          hp: order.hp_earned || 0,
          name: order.customer_name || undefined,
          headline: 'Order Confirmed',
          value: order.hp_earned > 0 ? `+${order.hp_earned} HP` : '',
          caption: 'I just ordered real flame-grilled goodness from Holy Grills 🔥',
          link: typeof window !== 'undefined' ? window.location.origin : '',
        }}
      />
    </div>
  );
}
