import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts';
import {
  DollarSign, ShoppingBag, Users, Flame, Download, Calendar, RefreshCw,
  TrendingUp, Gift, Store, ShoppingCart, AlertCircle, Building2, Plus,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { Card, Skeleton, EmptyState, SectionTitle, StatTile, BreakdownTiles, body } from './ui/AdminKit';
import {
  OrderTimingDashboard, AddonAcceptanceDashboard, DeliveryLocationDashboard,
  SquadOrdersDashboard, DemographicsDashboard, EngagementDashboard,
  PaymentMethodDashboard, RevenueDashboard, HpEcosystemDashboard,
  AcademicCalendarDashboard, OrderSourcesDashboard, ReferralNetworkDashboard,
  RetentionLtvDashboard,
} from './AdminAnalyticsDashboards';
import { toast } from '@/components/ui/use-toast';

const DASH_TABS = [
  { id: 'sales', label: 'Sales & Revenue' },
  { id: 'customers', label: 'Customers & Engagement' },
  { id: 'operations', label: 'Operations & Logistics' },
];

const COLORS = ['#E70E0E', '#F2B84B', '#6A1F00', '#FF9500', '#A8301A', '#C47B3A'];

const todayStr = () => new Date().toISOString().slice(0, 10);
const daysAgoStr = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };

// Analytics & Trends — the full /analytics surface: sales, orders, items,
// users, retention, hp, referrals, gifts, marketplace, abandoned-carts and
// CSV export. Every response is unwrapped defensively and rendered with
// honest empty states — no invented numbers.
export default function AdminAnalytics() {
  const [fromDate, setFromDate] = useState(daysAgoStr(30));
  const [toDate, setToDate] = useState(todayStr());
  const [sales, setSales] = useState(null);
  const [users, setUsers] = useState(null);
  const [hp, setHp] = useState(null);
  const [orders, setOrders] = useState(null);
  const [items, setItems] = useState([]);
  const [retention, setRetention] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [gifts, setGifts] = useState(null);
  const [marketplace, setMarketplace] = useState(null);
  const [abandoned, setAbandoned] = useState(null);
  const [exporting, setExporting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('sales');
  const [brandPartnerships, setBrandPartnerships] = useState([]);
  const [brandModal, setBrandModal] = useState(false);
  const [brandForm, setBrandForm] = useState({ brand_name: '', contact_email: '', requested_data: {} });
  const [brandBusy, setBrandBusy] = useState(false);

  const range = { from_date: fromDate, to_date: toDate };

  const load = async () => {
    setLoading(true);
    const [s, u, h, o, it, rt, rf, gf, mp, ab] = await Promise.allSettled([
      liveApi.analytics.sales(range),
      liveApi.analytics.users(range),
      liveApi.admin.getAnalyticsHp(),
      liveApi.analytics.orders(range),
      liveApi.analytics.items(range),
      liveApi.analytics.retention({ weeks: 12 }),
      liveApi.admin.getAnalyticsReferrals(),
      liveApi.analytics.gifts(),
      liveApi.analytics.marketplace(),
      liveApi.analytics.abandonedCarts(),
    ]);
    setSales(s.status === 'fulfilled' ? body(s.value) : null);
    setUsers(u.status === 'fulfilled' ? body(u.value) : null);
    setHp(h.status === 'fulfilled' ? h.value : null);
    setOrders(o.status === 'fulfilled' ? body(o.value) : null);
    if (it.status === 'fulfilled') { const v = body(it.value); setItems(Array.isArray(v) ? v : (v?.items || [])); } else setItems([]);
    setRetention(rt.status === 'fulfilled' ? body(rt.value) : null);
    setReferrals(rf.status === 'fulfilled' ? body(rf.value) : null);
    setGifts(gf.status === 'fulfilled' ? body(gf.value) : null);
    setMarketplace(mp.status === 'fulfilled' ? body(mp.value) : null);
    setAbandoned(ab.status === 'fulfilled' ? body(ab.value) : null);
    setLoading(false);
    // Brand partnerships — loaded separately (CRUD entity, not date-scoped).
    liveApi.analytics.getBrandPartnerships().then(setBrandPartnerships).catch(() => setBrandPartnerships([]));
  };

  useEffect(() => { load(); }, [fromDate, toDate]);

  const submitBrandPartnership = async () => {
    if (!brandForm.brand_name || !brandForm.contact_email) {
      toast({ title: 'Brand name and contact email are required', variant: 'destructive' });
      return;
    }
    setBrandBusy(true);
    try {
      await liveApi.analytics.createBrandPartnership(brandForm);
      toast({ title: 'Brand partnership logged' });
      setBrandModal(false);
      setBrandForm({ brand_name: '', contact_email: '', requested_data: {} });
      setBrandPartnerships(await liveApi.analytics.getBrandPartnerships());
    } catch (e) {
      toast({ title: 'Failed to log brand partnership', description: e.message, variant: 'destructive' });
    }
    setBrandBusy(false);
  };

  const updateBrandStatus = async (id, status) => {
    try {
      await liveApi.analytics.updateBrandPartnership(id, { status });
      setBrandPartnerships(await liveApi.analytics.getBrandPartnerships());
    } catch (e) {
      toast({ title: 'Failed to update', description: e.message, variant: 'destructive' });
    }
  };

  const setPreset = (days) => { setFromDate(daysAgoStr(days)); setToDate(todayStr()); };

  // GET /analytics/export?type=… → CSV text download (raw response, not JSON).
  const doExport = async (type) => {
    setExporting(type);
    try {
      const csv = await liveApi.admin.exportAnalytics(type, range);
      if (csv && typeof csv === 'string' && csv.trim()) {
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `${type}_${todayStr()}.csv`; a.click();
        URL.revokeObjectURL(url);
      } else {
        window.alert('Export returned no data for this date range.');
      }
    } catch (e) {
      window.alert(`Export failed: ${e.message}`);
    }
    setExporting(null);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <Skeleton className="h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  const EXPORTS = ['orders', 'hp_transactions', 'wallet_transactions', 'users'];
  const funnelRaw = orders?.status_funnel;
  const funnel = Array.isArray(funnelRaw)
    ? funnelRaw
    : Object.entries(funnelRaw || {}).map(([name, value]) => ({ name, value }));
  const retentionArr = Array.isArray(retention) ? retention : (retention?.retention || retention?.cohorts || []);

  const kpis = [
    { label: 'Revenue (Delivered)', value: formatNaira(sales?.total_revenue ?? 0), sub: `${sales?.order_count ?? 0} delivered orders`, icon: DollarSign, iconClass: 'text-success', iconBg: 'bg-success/15' },
    { label: 'Total Orders', value: orders?.total_orders ?? orders?.total ?? orders?.order_count ?? sales?.order_count ?? 0, sub: `${fromDate} → ${toDate}`, icon: ShoppingBag, iconClass: 'text-primary', iconBg: 'bg-primary/10' },
    { label: 'Active Users', value: users?.dau ?? 0, sub: `DAU · MAU ${users?.mau ?? 0}`, icon: Users, iconClass: 'text-accent-foreground', iconBg: 'bg-accent/25' },
    { label: 'HP in Circulation', value: (hp?.hp_in_circulation ?? 0).toLocaleString(), sub: `Earned ${(hp?.hp_earned_active ?? 0).toLocaleString()} · Spent ${(hp?.hp_spent ?? 0).toLocaleString()}`, icon: Flame, iconClass: 'text-destructive', iconBg: 'bg-destructive/10' },
  ];

  return (
    <div className="space-y-4">
      {/* Date range + presets — always visible */}
      <Card className="p-4 flex flex-col lg:flex-row lg:items-center gap-3">
        <div className="flex items-center gap-2 text-sm font-extrabold text-foreground shrink-0">
          <Calendar className="w-4 h-4 text-primary" /> Date Range
        </div>
        <div className="flex gap-1.5 shrink-0">
          {[7, 30, 90].map((d) => (
            <button key={d} onClick={() => setPreset(d)} className="px-3 py-1.5 rounded-full text-xs font-bold bg-secondary text-secondary-foreground hover:bg-primary/10 hover:text-primary active:scale-95 transition">
              {d}d
            </button>
          ))}
        </div>
        <div className="flex-1 grid grid-cols-2 gap-3 max-w-xs">
          <div>
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">From</label>
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="w-full mt-0.5 px-3 py-2 rounded-xl border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div>
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">To</label>
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="w-full mt-0.5 px-3 py-2 rounded-xl border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">AOV</div>
          <div className="font-heading font-extrabold text-lg text-foreground">{formatNaira(sales?.average_order_value ?? sales?.avg_order_value ?? 0)}</div>
        </div>
      </Card>

      {/* KPIs — headline metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k, i) => (
          <motion.div key={k.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.3 }}>
            <StatTile {...k} />
          </motion.div>
        ))}
      </div>

      {/* 3 consolidated tabs */}
      <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide pb-1">
        {DASH_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition ${tab === t.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card border border-border text-muted-foreground hover:text-foreground'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'sales' && (
      <>
      <Card className="p-4">
        <SectionTitle icon={Download} title="Export (CSV)" sub={`${fromDate} → ${toDate} · GET /analytics/export`} />
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map((t) => (
            <button key={t} onClick={() => doExport(t)} disabled={exporting === t} className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary active:scale-95 transition disabled:opacity-50">
              <Download className="w-3 h-3" /> {exporting === t ? 'Exporting…' : t.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle icon={TrendingUp} title="Orders by Status (Funnel)" sub="GET /analytics/orders" />
        {funnel.length === 0 ? (
          <EmptyState icon={ShoppingBag} title="No orders in this range" body="The funnel fills in as orders move through the pipeline." />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnel.map((f) => ({ name: (f.name || f.status || '').replace(/_/g, ' '), value: f.value ?? f.count ?? 0 }))} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} angle={-15} textAnchor="end" height={60} interval={0} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {funnel.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card className="p-5">
        <SectionTitle icon={DollarSign} title="Item Performance" sub="Revenue per item in range" />
        {items.length === 0 ? (
          <EmptyState icon={DollarSign} title="No item sales in this range" />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={items.slice(0, 8).map((it) => ({ name: (it.name_snapshot || it.item_name || it.name || '').replace(/🔥/g, '').trim(), revenue: it.total_revenue ?? it.revenue ?? 0 }))} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} interval={0} angle={-15} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} tickFormatter={(v) => `₦${(v / 1000).toFixed(0)}k`} />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} formatter={(v) => formatNaira(v)} />
                <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
                  {items.slice(0, 8).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <RevenueDashboard />
      <PaymentMethodDashboard />
      <AddonAcceptanceDashboard />
      <OrderSourcesDashboard />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={Store} title="Marketplace" sub="Purchases + code inventory · GET /analytics/marketplace" />
          <BreakdownTiles data={marketplace} emptyTitle="No marketplace activity yet." />
        </Card>
        <Card className="p-5">
          <SectionTitle icon={ShoppingCart} title="Abandoned Carts" sub="Total / recovered / unrecovered · GET /analytics/abandoned-carts" />
          <BreakdownTiles data={abandoned} emptyTitle="No abandoned carts in this range." />
        </Card>
      </div>
      </>
      )}

      {tab === 'customers' && (
      <>
      <Card className="p-5">
        <SectionTitle icon={Users} title="Cohort Retention" sub="Share of users who ordered again · GET /analytics/retention" />
        {retentionArr.length === 0 && retention == null ? (
          <EmptyState icon={Users} title="No retention data yet" body="Cohorts appear once repeat orders start landing." />
        ) : Array.isArray(retentionArr) && retentionArr.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[420px]">
              <thead>
                <tr className="text-muted-foreground text-xs border-b border-border">
                  <th className="text-left py-2 font-extrabold">Cohort</th>
                  <th className="py-2 font-extrabold">Users</th>
                  <th className="py-2 font-extrabold">Retained</th>
                  <th className="py-2 font-extrabold">Retention</th>
                </tr>
              </thead>
              <tbody>
                {retentionArr.map((r, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2.5 text-foreground font-bold">{r.cohort_week || r.cohort}</td>
                    <td className="text-center py-2.5 text-muted-foreground font-extrabold">{r.total_users ?? '—'}</td>
                    <td className="text-center py-2.5 text-accent-foreground font-extrabold">{r.retained_users ?? '—'}</td>
                    <td className="text-center py-2.5 text-success font-extrabold">{r.retention_pct != null ? `${r.retention_pct}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <BreakdownTiles data={retention} emptyTitle="No retention data for this range yet." formatValue={(v) => `${v}%`} />
        )}
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={Users} title="Referral Funnel" sub="GET /analytics/referrals" />
          <BreakdownTiles data={referrals} emptyTitle="No referral activity in this range yet." />
        </Card>
        <Card className="p-5">
          <SectionTitle icon={Gift} title="First-Order Gifts" sub="Gift status breakdown · GET /analytics/gifts" />
          <BreakdownTiles data={gifts} emptyTitle="No first-order gifts recorded yet." />
        </Card>
      </div>

      <RetentionLtvDashboard />
      <ReferralNetworkDashboard />

      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <SectionTitle icon={Building2} title="Brand Partnerships" sub="Log and track brand data-sharing requests · GET/POST/PATCH /analytics/brand-partnerships" />
          <button onClick={() => setBrandModal(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition">
            <Plus className="w-3.5 h-3.5" /> Log request
          </button>
        </div>
        {brandPartnerships.length === 0 ? (
          <EmptyState icon={Building2} title="No brand partnership requests yet" body="Log a brand's data request for record keeping." />
        ) : (
          <div className="space-y-2">
            {brandPartnerships.map((b) => (
              <div key={b.id} className="flex items-center gap-3 p-3 rounded-xl border border-border">
                <div className="flex-1">
                  <div className="font-bold text-sm text-foreground">{b.brand_name}</div>
                  <div className="text-xs text-muted-foreground">{b.contact_email} · {new Date(b.created_at).toLocaleDateString()}</div>
                </div>
                {b.status === 'pending' ? (
                  <div className="flex gap-1">
                    <button onClick={() => updateBrandStatus(b.id, 'approved')} className="px-3 py-1.5 rounded-full bg-green-50 text-green-600 border border-green-200 text-xs font-bold active:scale-95">Approve</button>
                    <button onClick={() => updateBrandStatus(b.id, 'rejected')} className="px-3 py-1.5 rounded-full bg-red-50 text-red-600 border border-red-200 text-xs font-bold active:scale-95">Reject</button>
                  </div>
                ) : (
                  <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${b.status === 'approved' ? 'bg-success/15 text-success' : 'bg-destructive/10 text-destructive'}`}>{b.status}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <DemographicsDashboard />
      <EngagementDashboard />
      <SquadOrdersDashboard />
      <HpEcosystemDashboard />
      </>
      )}

      {tab === 'operations' && (
      <>
      <OrderTimingDashboard />
      <DeliveryLocationDashboard />
      <AcademicCalendarDashboard />
      </>
      )}

      {brandModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setBrandModal(false)}>
          <div className="bg-card rounded-2xl p-5 w-full max-w-md space-y-3 shadow-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-bold text-sm text-foreground">Log Brand Partnership Request</h3>
            <div>
              <label className="text-xs font-bold text-muted-foreground">Brand name</label>
              <input value={brandForm.brand_name} onChange={(e) => setBrandForm({ ...brandForm, brand_name: e.target.value })} className="w-full mt-1 px-3 py-2 rounded-xl border border-border text-sm" placeholder="Acme Foods" />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground">Contact email</label>
              <input value={brandForm.contact_email} onChange={(e) => setBrandForm({ ...brandForm, contact_email: e.target.value })} className="w-full mt-1 px-3 py-2 rounded-xl border border-border text-sm" placeholder="contact@acme.com" />
            </div>
            <div>
              <label className="text-xs font-bold text-muted-foreground">Requested data (JSON)</label>
              <textarea value={JSON.stringify(brandForm.requested_data, null, 2)} onChange={(e) => { try { setBrandForm({ ...brandForm, requested_data: JSON.parse(e.target.value || '{}') }); } catch { /* invalid JSON — keep previous */ } }} className="w-full mt-1 px-3 py-2 rounded-xl border border-border text-sm font-mono min-h-[80px]" placeholder='{"sales_summary": true}' />
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setBrandModal(false)} className="flex-1 py-2.5 rounded-full bg-secondary text-foreground text-sm font-bold">Cancel</button>
              <button onClick={submitBrandPartnership} disabled={brandBusy} className="flex-1 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50">{brandBusy ? 'Saving…' : 'Log request'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}