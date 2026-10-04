import React, { useState, useEffect } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronRight, Package, Flame } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira, timeAgo, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/lib/hgUtils';
import { fadeUp, staggerContainer } from '@/lib/animationPresets';
import MascotStandee from '@/components/mascot/MascotStandee';

function OrderCard({ order, onClick, active = false }) {
  return (
    <motion.button
      variants={fadeUp}
      onClick={onClick}
      whileTap={{ scale: 0.98 }}
      className={`w-full text-left rounded-2xl border p-4 transition-all ${active ? 'bg-primary/5 border-primary/30' : 'bg-card border-border hover:border-primary/30 hover:shadow-card'}`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${ORDER_STATUS_COLORS[order.status] || 'bg-muted text-muted-foreground'}`}>
          {ORDER_STATUS_LABELS[order.status] || order.status}
        </span>
        <span className="text-xs text-muted-foreground">{timeAgo(order.created_at)}</span>
      </div>
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        {(order.order_items || []).slice(0, 3).map((item, i) => (
          <span key={i} className="text-xs text-muted-foreground">
            {item.quantity}× {item.name_snapshot}{i < Math.min(order.order_items.length, 3) - 1 ? ',' : ''}
          </span>
        ))}
        {order.order_items?.length > 3 && <span className="text-xs text-muted-foreground">+{order.order_items.length - 3}</span>}
      </div>
      <div className="flex items-center justify-between">
        <span className="font-heading font-bold text-foreground">{formatNaira(order.total_amount)}</span>
        {order.hp_earned > 0 && (
          <span className="flex items-center gap-1 text-xs font-bold text-primary">
            <Flame className="w-3 h-3" />+{order.hp_earned} HP
          </span>
        )}
      </div>
    </motion.button>
  );
}

// Guests are redirected to /track-orders, which carries the guest tracking
// experience (order number + tracking code lookup + saved guest orders). This
// page only serves the authenticated order history.
export default function Orders() {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [loading, setLoading] = useState(true);
  const [orders, setOrders] = useState([]);
  const [dateFilter, setDateFilter] = useState('all');
  const [activeOrders, setActiveOrders] = useState([]);

  useEffect(() => {
    if (!isAuthenticated) { setLoading(false); return; }
    const load = async () => {
      try {
        const [all, active] = await Promise.all([
          mockApi.orders.list({ limit: 20 }),
          mockApi.orders.getActive().catch(() => []),
        ]);
        setOrders(all);
        setActiveOrders(Array.isArray(active) ? active : (active ? [active] : []));
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, [isAuthenticated]);

  if (!isAuthenticated) return <Navigate to="/track-orders" replace />;

  if (loading) {
    return (
      <div className="space-y-3 animate-fade-in">
        <div className="h-8 w-32 bg-muted rounded animate-pulse" />
        <div className="flex gap-2">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-8 w-20 bg-muted rounded-full animate-pulse" />)}
        </div>
        {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 bg-muted rounded-2xl animate-pulse" />)}
      </div>
    );
  }

  const now = Date.now();
  const dateCutoff = (range) => {
    if (range === '7d') return now - 7 * 86400000;
    if (range === '30d') return now - 30 * 86400000;
    if (range === '90d') return now - 90 * 86400000;
    return 0;
  };
  const inDateRange = (o) => new Date(o.created_at).getTime() >= dateCutoff(dateFilter);
  const liveActive = activeOrders.length > 0
    ? activeOrders
    : orders.filter((o) => !['delivered', 'cancelled', 'refunded'].includes(o.status));
  const pastOrders = orders.filter((o) => ['delivered', 'cancelled', 'refunded'].includes(o.status) && inDateRange(o));

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <span className="hg-eyebrow">Your history</span>
          <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">My Orders</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Every plate, remembered.</p>
        </div>
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={() => navigate('/track-orders')}
          className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow"
        >
          <Package className="w-3.5 h-3.5" /> Track Orders
        </motion.button>
      </div>

      {/* Date Filter Pills */}
      <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 pb-1">
        {[
          { id: 'all', label: 'All Time' },
          { id: '7d', label: 'Last 7 Days' },
          { id: '30d', label: 'Last Month' },
          { id: '90d', label: 'Last 3 Months' },
        ].map((d) => (
          <button
            key={d.id}
            onClick={() => setDateFilter(d.id)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-bold transition-all ${dateFilter === d.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-muted-foreground border border-border'}`}
          >
            {d.label}
          </button>
        ))}
      </div>

      {/* Active Orders */}
      {liveActive.length > 0 && (
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-2">Active Orders</h2>
          <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show" className="space-y-2">
            {liveActive.map((order) => (
              <OrderCard key={order.id} order={order} onClick={() => navigate(`/orders/${order.id}`)} active />
            ))}
          </motion.div>
        </div>
      )}

      {/* Past Orders */}
      <div>
        {pastOrders.length > 0 && (
          <h2 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-2">Past Orders</h2>
        )}
        {pastOrders.length === 0 ? (
          <div className="text-center py-12 space-y-3">
            <MascotStandee mascot="waving" className="w-32 h-32 mx-auto" alt="No active orders" />
            <p className="text-sm text-muted-foreground">No orders yet.</p>
            <button onClick={() => navigate('/menu')} className="px-4 py-2 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">Browse Menu</button>
          </div>
        ) : (
          <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show" className="space-y-2">
            {pastOrders.map((order) => (
              <OrderCard key={order.id} order={order} onClick={() => navigate(`/orders/${order.id}`)} />
            ))}
          </motion.div>
        )}
      </div>
    </div>
  );
}