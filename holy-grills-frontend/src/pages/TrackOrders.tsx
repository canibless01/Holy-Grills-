import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronLeft, Check, Package, Clock, Search, AlertCircle, Mail } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira, formatDateTime, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS, ORDER_STATUS_FLOW } from '@/lib/hgUtils';
import { fadeUp, staggerContainer } from '@/lib/animationPresets';
import ScheduledOrders from '@/components/ScheduledOrders';

const DONE = ['delivered', 'cancelled', 'refunded'];
const POLL_MS = 30000;

function TrackSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="rounded-2xl bg-card border border-border overflow-hidden">
          <div className="h-20 bg-muted animate-pulse" />
          <div className="p-4 space-y-3">
            <div className="h-6 bg-muted rounded animate-pulse" />
            <div className="flex gap-1.5">
              {Array.from({ length: 6 }).map((_, j) => <div key={j} className="w-7 h-7 bg-muted rounded-full animate-pulse" />)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Turn the backend's claim failures into something a guest can act on.
function describeLookupError(e) {
  const msg = e?.message || '';
  if (msg.includes('INVALID_CLAIM')) return 'That tracking code doesn\'t match this order. Check the code in your email.';
  if (msg.includes('ACCESS_DENIED')) return 'This order is already linked to an account. Log in to track it.';
  if (msg.includes('404') || msg.toLowerCase().includes('not found')) return 'We couldn\'t find an order with that number.';
  return msg || 'Could not find that order.';
}

export default function TrackOrders() {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [loading, setLoading] = useState(true);
  const [activeOrders, setActiveOrders] = useState([]);
  const [guestOrders, setGuestOrders] = useState([]);
  const [lookupId, setLookupId] = useState('');
  const [lookupToken, setLookupToken] = useState('');
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupError, setLookupError] = useState(null);

  // Collate EVERY undelivered order — not just the single "active" one —
  // so the page shows all in-progress orders and their timelines together.
  const load = useCallback(async () => {
    let mine = [];
    if (isAuthenticated) {
      const all = await mockApi.orders.list({ limit: 50 }).catch(() => []);
      mine = (Array.isArray(all) ? all : []).filter((o) => !DONE.includes(o.status));
    }
    setActiveOrders(mine);

    // Guest orders live only on this device (saved at checkout). They are never
    // in the account list, so each is read back with its own claim token.
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem('hg_guest_orders') || '[]'); } catch { saved = []; }
    const claimedIds = new Set(mine.map((o) => o.id));
    const fetched = await Promise.all(
      (Array.isArray(saved) ? saved : []).slice(0, 10).map(async (g) => {
        if (!g?.id || claimedIds.has(g.id)) return null;
        try {
          const o = await mockApi.orders.get(g.id, g.claim_token ? { claim_token: g.claim_token } : {});
          return o ? { ...o, claim_token: g.claim_token } : null;
        } catch { return null; }
      })
    );
    setGuestOrders(fetched.filter(Boolean).filter((o) => !DONE.includes(o.status)));
    setLoading(false);
  }, [isAuthenticated]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  // A guest on a new device (or who lost the email) can enter the order number
  // and tracking code from their confirmation email to pick the order back up.
  const handleLookup = async (e) => {
    e.preventDefault();
    const id = lookupId.trim();
    const token = lookupToken.trim();
    if (!id || !token) { setLookupError('Enter both your order number and tracking code.'); return; }
    setLookupBusy(true);
    setLookupError(null);
    try {
      await mockApi.orders.get(id, { claim_token: token });
      navigate(`/orders/${encodeURIComponent(id)}?claim_token=${encodeURIComponent(token)}`);
    } catch (err) {
      setLookupError(describeLookupError(err));
    }
    setLookupBusy(false);
  };

  const all = [...guestOrders, ...activeOrders];

  return (
    <div className="space-y-4 animate-fade-in pb-4">
      <button onClick={() => navigate(isAuthenticated ? '/orders' : '/menu')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> {isAuthenticated ? 'Back to orders' : 'Back to menu'}
      </button>

      <div>
        <span className="hg-eyebrow">Live tracking</span>
        <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">Track Orders</h1>
        <p className="text-sm text-muted-foreground mt-0.5">{all.length} active order{all.length !== 1 ? 's' : ''} in progress</p>
      </div>

      {/* Guest lookup — order number + tracking code from the confirmation email */}
      {!isAuthenticated && (
        <form onSubmit={handleLookup} className="rounded-2xl bg-card border border-border p-4 space-y-3 shadow-card">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-primary" />
            <span className="text-sm font-bold text-foreground">Track a guest order</span>
          </div>
          <p className="text-xs text-muted-foreground">Enter the order number and tracking code from your confirmation email.</p>
          <input
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            placeholder="Order number"
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <input
            value={lookupToken}
            onChange={(e) => setLookupToken(e.target.value)}
            placeholder="Tracking code"
            className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-secondary text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {lookupError && (
            <div className="flex items-start gap-2 rounded-xl bg-destructive/10 border border-destructive/20 p-3">
              <AlertCircle className="w-4 h-4 text-destructive shrink-0 mt-0.5" />
              <span className="text-xs text-destructive font-medium">{lookupError}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={lookupBusy}
            className="w-full py-3 rounded-xl bg-gradient-cta text-white text-sm font-bold shadow-glow flex items-center justify-center gap-1.5 disabled:opacity-60"
          >
            <Search className="w-4 h-4" /> {lookupBusy ? 'Looking up…' : 'Track order'}
          </button>
        </form>
      )}

      {loading ? (
        <TrackSkeleton />
      ) : all.length === 0 ? (
        <div className="text-center py-16 space-y-3">
          <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto">
            <Package className="w-8 h-8 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">No active orders right now</p>
          <button onClick={() => navigate('/menu')} className="px-5 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">Order now</button>
        </div>
      ) : (
        <motion.div variants={staggerContainer(0.06)} initial="hidden" animate="show" className="space-y-3">
          {all.map((order) => {
            const statusIndex = ORDER_STATUS_FLOW.indexOf(order.status);
            const isGuest = !!order.claim_token && !order.user_id;
            const href = `/orders/${order.id}${isGuest ? `?claim_token=${encodeURIComponent(order.claim_token)}` : ''}`;
            return (
              <motion.div key={order.id} variants={fadeUp} className="rounded-2xl bg-card border border-border overflow-hidden shadow-card hover:shadow-glow transition-shadow">
                {/* Header */}
                <div className="flex items-center justify-between p-4 bg-gradient-dark text-white">
                  <div>
                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${ORDER_STATUS_COLORS[order.status]}`}>
                      {ORDER_STATUS_LABELS[order.status]}
                    </span>
                    <div className="text-xs text-white/70 mt-1 flex items-center gap-1.5">
                      #{(order.order_number || order.id || '').toUpperCase()}
                      {isGuest && <span className="px-1.5 py-0.5 rounded bg-white/15 text-[9px] font-bold">GUEST</span>}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-heading font-bold text-sm">{formatNaira(order.total_amount)}</div>
                    <div className="text-[10px] text-white/70 flex items-center gap-1 justify-end mt-0.5">
                      <Clock className="w-3 h-3" /> {formatDateTime(order.created_at)}
                    </div>
                  </div>
                </div>

                {/* Timeline */}
                {order.status !== 'cancelled' && order.status !== 'refunded' && (
                  <div className="px-4 py-4">
                    <div className="flex items-center gap-0.5">
                      {ORDER_STATUS_FLOW.map((step, i) => (
                        <React.Fragment key={step}>
                          <div className={`flex flex-col items-center ${i <= statusIndex ? 'text-primary' : 'text-muted-foreground'}`}>
                            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${i <= statusIndex ? 'bg-gradient-cta text-white' : 'bg-muted text-muted-foreground'}`}>
                              {i < statusIndex ? <Check className="w-3.5 h-3.5 text-white" /> : i + 1}
                            </div>
                            <span className="text-[8px] mt-1 font-semibold whitespace-nowrap">{ORDER_STATUS_LABELS[step].split(' ')[0]}</span>
                          </div>
                          {i < ORDER_STATUS_FLOW.length - 1 && (
                            <div className={`flex-1 h-0.5 rounded-full ${i < statusIndex ? 'bg-primary' : 'bg-border'}`} />
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                  </div>
                )}

                {/* Items preview */}
                <div className="px-4 pb-3">
                  <div className="flex flex-wrap gap-1.5">
                    {(order.order_items || []).slice(0, 3).map((item, i) => (
                      <span key={i} className="text-[11px] text-muted-foreground bg-muted px-2 py-1 rounded-md">
                        {item.quantity}× {item.name_snapshot}
                      </span>
                    ))}
                    {order.order_items?.length > 3 && (
                      <span className="text-[11px] text-muted-foreground bg-muted px-2 py-1 rounded-md">+{order.order_items.length - 3}</span>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => navigate(href)}
                  className="w-full py-3 text-xs font-bold text-primary border-t border-border hover:bg-primary/5 transition-colors"
                >
                  View details →
                </button>
              </motion.div>
            );
          })}
        </motion.div>
      )}

      <ScheduledOrders />
    </div>
  );
}