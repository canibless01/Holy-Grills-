import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import {
  Package, DollarSign, Activity, CheckCircle2, Flame, TrendingUp, Truck, Clock,
  RefreshCw, BarChart3, Gauge, AlertCircle, UtensilsCrossed, Users,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { Card, Skeleton, StatTile, EmptyState, SectionTitle, Pill, body } from './ui/AdminKit';

const FLAME = ['#E70E0E', '#F2B84B', '#FF9500', '#6A1F00', '#A8301A', '#C47B3A'];
const STATUS_COLORS = ['#94a3b8', '#E70E0E', '#F2B84B', '#3b82f6', '#06b6d4', '#22c55e'];

const todayStr = () => new Date().toISOString().slice(0, 10);
const daysAgoStr = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };

// Dashboard Overview — GET /analytics/dashboard (today's pipeline, batch
// status, revenue snapshot) + /analytics/sales|users|items (30d) +
// /analytics/hp via admin.getAnalyticsHp + /menu/kitchen-capacity.
// Auto-refreshes every 30s. Every field is guarded — live values render
// where the shape matches, honest zeros otherwise.
export default function AdminDashboard() {
  const [data, setData] = useState(null);
  const [sales, setSales] = useState(null);
  const [users, setUsers] = useState(null);
  const [hp, setHp] = useState(null);
  const [items, setItems] = useState([]);
  const [capacity, setCapacity] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async () => {
    const range = { from_date: daysAgoStr(30), to_date: todayStr() };
    const [d, s, u, h, it, cap] = await Promise.allSettled([
      liveApi.analytics.dashboard(),
      liveApi.analytics.sales(range),
      liveApi.analytics.users(range),
      liveApi.admin.getAnalyticsHp(),
      liveApi.analytics.items(range),
      liveApi.menu.getKitchenCapacity(),
    ]);
    setData(d.status === 'fulfilled' ? body(d.value) : null);
    setSales(s.status === 'fulfilled' ? body(s.value) : null);
    setUsers(u.status === 'fulfilled' ? body(u.value) : null);
    setHp(h.status === 'fulfilled' ? h.value : null);
    if (it.status === 'fulfilled') {
      const v = body(it.value);
      setItems(Array.isArray(v) ? v : (v?.items || []));
    } else setItems([]);
    setCapacity(cap.status === 'fulfilled' ? body(cap.value) : null);
    setLoading(false);
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (!data && !sales && !users && !hp && items.length === 0 && !capacity) {
    return (
      <Card>
        <EmptyState
          icon={AlertCircle}
          title="Analytics unavailable right now"
          body="The dashboard endpoints didn't respond. Check your session and retry."
          action={
            <button onClick={load} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          }
        />
      </Card>
    );
  }

  const d = data || {};
  const stats = [
    { label: 'Orders Today', value: d.total_orders ?? d.today?.total_orders ?? 0, icon: Package, iconClass: 'text-primary', iconBg: 'bg-primary/10' },
    { label: 'Revenue Delivered (Today)', value: formatNaira(d.revenue_delivered ?? d.today?.revenue_delivered ?? 0), icon: DollarSign, iconClass: 'text-success', iconBg: 'bg-success/15' },
    { label: 'Active Orders', value: d.active_orders ?? d.today?.active_orders ?? 0, icon: Activity, iconClass: 'text-accent-foreground', iconBg: 'bg-accent/25' },
    { label: 'Delivered Today', value: d.delivered_orders ?? d.today?.delivered_orders ?? 0, icon: CheckCircle2, iconClass: 'text-success', iconBg: 'bg-success/15' },
  ];

  const statusData = Object.entries(d.orders_by_status ?? d.today?.orders_by_status ?? {})
    .map(([name, value], i) => ({ name: name.replace(/_/g, ' '), value, fill: STATUS_COLORS[i % STATUS_COLORS.length] }));
  const paymentData = Object.entries(d.orders_by_payment_method ?? d.today?.orders_by_payment_method ?? {})
    .map(([name, value]) => ({ name, value }));
  const itemsData = items.slice(0, 6).map((it) => ({
    name: (it.name_snapshot || it.item_name || it.name || '').replace(/🔥/g, '').trim(),
    quantity: it.qty_sold ?? it.total_quantity ?? it.quantity ?? 0,
  }));
  const tierData = Object.entries(users?.tier_breakdown ?? users?.tier_distribution ?? hp?.tier_distribution ?? {})
    .map(([name, value], i) => ({ name, value, fill: FLAME[i % FLAME.length] }));
  const opsOpenWindows = (d.open_windows ?? []).length;
  const opsActiveBatches = (d.active_batches ?? []).length;
  const opsUnassigned = d.unassigned_orders ?? 0;
  const dailyCapacity = capacity ? (capacity.daily_order_capacity ?? capacity.daily_capacity ?? capacity.max_daily_orders ?? null) : null;

  return (
    <div className="space-y-4">
      {/* Header strip */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-primary" />
          <span className="hg-eyebrow">Today, at a glance</span>
        </div>
        <div className="flex items-center gap-2">
          <Pill tone="green">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> Auto-refresh 30s
          </Pill>
          {lastUpdated && <span className="text-[10px] font-semibold text-muted-foreground">Updated {lastUpdated.toLocaleTimeString()}</span>}
          <button onClick={load} className="p-2 rounded-xl bg-card border border-border text-muted-foreground hover:text-primary hover:border-primary/40 active:scale-95 transition" title="Refresh now">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.3 }}>
            <StatTile {...s} />
          </motion.div>
        ))}
      </div>

      {/* 30d sales summary */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <SectionTitle icon={TrendingUp} title="Sales — last 30 days (delivered)" sub="GET /analytics/sales summary" />
          <div className="text-right">
            <div className="font-heading font-extrabold text-xl text-foreground">{formatNaira(sales?.total_revenue ?? 0)}</div>
            <div className="text-xs text-muted-foreground font-semibold">{sales?.order_count ?? 0} orders · AOV {formatNaira(sales?.average_order_value ?? sales?.avg_order_value ?? 0)}</div>
          </div>
        </div>
      </Card>

      {/* Charts */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={Package} title="Orders by Status" sub="Today" />
          {statusData.length === 0 ? (
            <EmptyState icon={Package} title="No orders today" body="The pipeline will light up as orders arrive." />
          ) : (
            <>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={statusData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={52} outerRadius={80} paddingAngle={2}>
                      {statusData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                    </Pie>
                    <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="grid grid-cols-2 gap-1.5 mt-2">
                {statusData.map((s) => (
                  <div key={s.name} className="flex items-center gap-1.5 text-xs">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: s.fill }} />
                    <span className="capitalize text-muted-foreground truncate">{s.name}</span>
                    <span className="font-extrabold text-foreground ml-auto">{s.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card className="p-5">
          <SectionTitle icon={DollarSign} title="Payment Methods" sub="Today" />
          {paymentData.length === 0 ? (
            <EmptyState icon={DollarSign} title="No payments today" />
          ) : (
            <div className="h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={paymentData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
                  <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {paymentData.map((_, i) => <Cell key={i} fill={FLAME[i % FLAME.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={UtensilsCrossed} title="Top Items" sub="30d delivered · GET /analytics/items" />
          {itemsData.length === 0 ? (
            <EmptyState icon={UtensilsCrossed} title="No item sales yet" body="Item performance appears once orders are delivered." />
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={itemsData} layout="vertical" margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} />
                  <Bar dataKey="quantity" radius={[0, 6, 6, 0]} fill="#E70E0E" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle icon={Flame} title="Users by Tier" sub="GET /analytics/users" />
            {tierData.length === 0 ? (
              <EmptyState icon={Users} title="No tier data yet" />
            ) : (
              <div className="flex items-center gap-4">
                <div className="h-36 w-36 shrink-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={tierData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={64} innerRadius={38} paddingAngle={2}>
                        {tierData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                      </Pie>
                      <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex-1 space-y-1.5">
                  {tierData.map((t) => (
                    <div key={t.name} className="flex items-center gap-2 text-xs">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: t.fill }} />
                      <span className="capitalize text-muted-foreground truncate">{t.name}</span>
                      <span className="font-extrabold text-foreground ml-auto">{t.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* HP Economy — /analytics/hp summary */}
          <div className="rounded-2xl bg-gradient-dark p-5 text-white shadow-card">
            <div className="flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-accent" />
              <h3 className="font-extrabold text-sm">HP Economy</h3>
              <span className="ml-auto text-[10px] font-bold text-white/50 uppercase tracking-wide">30d</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><div className="text-white/60 text-[10px] font-bold uppercase tracking-wide">Earned (active)</div><div className="font-extrabold">{(hp?.hp_earned_active ?? 0).toLocaleString()}</div></div>
              <div><div className="text-white/60 text-[10px] font-bold uppercase tracking-wide">Spent</div><div className="font-extrabold">{(hp?.hp_spent ?? 0).toLocaleString()}</div></div>
              <div><div className="text-white/60 text-[10px] font-bold uppercase tracking-wide">Expired</div><div className="font-extrabold text-accent">{(hp?.hp_expired ?? 0).toLocaleString()}</div></div>
              <div><div className="text-white/60 text-[10px] font-bold uppercase tracking-wide">In Circulation</div><div className="font-extrabold">{(hp?.hp_in_circulation ?? 0).toLocaleString()}</div></div>
            </div>
          </div>
        </div>
      </div>

      {/* Operations snapshot — all from /analytics/dashboard (+ capacity from /menu/kitchen-capacity) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Clock} label="Open delivery windows" value={opsOpenWindows} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
        <StatTile icon={Truck} label="Active batches" value={opsActiveBatches} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={Package} label="Unassigned orders" value={opsUnassigned} iconClass="text-destructive" iconBg="bg-destructive/10" />
        {dailyCapacity != null && (
          <StatTile icon={Gauge} label="Kitchen capacity" value={`${dailyCapacity}/day`} iconClass="text-success" iconBg="bg-success/15" />
        )}
      </div>
    </div>
  );
}