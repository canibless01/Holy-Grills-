import React, { useState, useEffect, useCallback } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import {
  Clock, Layers, MapPin, Users, GraduationCap, Activity, CreditCard, TrendingUp,
  Flame, DollarSign, Package, AlertCircle, CalendarDays, Radio, Share2, Repeat,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { Card, Skeleton, EmptyState, SectionTitle, StatTile, body } from './ui/AdminKit';

const COLORS = ['#E70E0E', '#F2B84B', '#6A1F00', '#FF9500', '#A8301A', '#C47B3A'];
const TIER_COLORS = { ember: '#A8301A', flame: '#E70E0E', blaze: '#F2B84B', holy: '#FFD700' };
const TIER_LABELS = { ember: 'Ember', flame: 'Flame', blaze: 'Blaze', holy: 'Holy' };

const todayStr = () => new Date().toISOString().slice(0, 10);
const daysAgoStr = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };

// Shared chart tooltip style
const tooltipStyle = { borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' };

// ── Generic horizontal bar list (top N items) ──
function HBarList({ data, valueKey = 'value', nameKey = 'name', formatValue = (v) => v, emptyTitle = 'No data yet' }) {
  const arr = Array.isArray(data) ? data : [];
  if (!arr.length) return <EmptyState icon={AlertCircle} title={emptyTitle} />;
  const max = Math.max(...arr.map((d) => d[valueKey] || 0), 1);
  return (
    <div className="space-y-2">
      {arr.slice(0, 10).map((d, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs font-bold text-foreground w-24 truncate shrink-0">{d[nameKey]}</span>
          <div className="flex-1 h-6 rounded-lg bg-secondary overflow-hidden">
            <div className="h-full rounded-lg transition-all" style={{ width: `${((d[valueKey] || 0) / max) * 100}%`, background: COLORS[i % COLORS.length] }} />
          </div>
          <span className="text-xs font-bold text-muted-foreground w-16 text-right tabular-nums shrink-0">{formatValue(d[valueKey] || 0)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Generic pie chart ──
function SimplePie({ data, formatValue }: {
  data?: Array<Record<string, unknown>>;
  formatValue?: (v: number) => React.ReactNode;
}) {
  if (!data || data.length === 0) return <EmptyState icon={AlertCircle} title="No data yet" />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${formatValue ? formatValue(value) : value}`}>
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Hook: fetch a single endpoint on mount ──
function useDashboard(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setData(body(await fetcher())); } catch (e) { setError(e.message); setData(null); }
    setLoading(false);
  }, deps);
  useEffect(() => { load(); }, [load]);
  return { data, loading, error };
}

function DashLoader() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 1. ORDER TIMING — bar (by day), line (by hour), line (30-day trend), KPIs
// ════════════════════════════════════════════════════════
export function OrderTimingDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.orderTiming());
  if (loading) return <DashLoader />;
  const byDay = data?.by_day || data?.orders_by_day || [];
  const byHour = data?.by_hour || data?.orders_by_hour || [];
  const trend = data?.trend || data?.daily_trend || [];
  const peakHour = data?.peak_hour ?? '—';
  const peakDay = data?.peak_day ?? '—';
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={Clock} label="Peak Hour" value={peakHour} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={Clock} label="Peak Day" value={peakDay} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
      </div>
      {byDay.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Clock} title="Orders by Day of Week" />
          <div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={byDay} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="orders" fill={COLORS[0]} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {byHour.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Clock} title="Orders by Hour" />
          <div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <LineChart data={byHour} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="orders" stroke={COLORS[0]} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {trend.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={TrendingUp} title="30-Day Order Trend" />
          <div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="orders" stroke={COLORS[1]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {byDay.length === 0 && byHour.length === 0 && trend.length === 0 && (
        <Card className="p-6"><EmptyState icon={Clock} title="No order timing data yet" body="Charts appear once orders start coming in." /></Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 2. ADD-ON ACCEPTANCE — KPIs, horizontal bar (popularity), pie (revenue split)
// ════════════════════════════════════════════════════════
export function AddonAcceptanceDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.addonAcceptance());
  if (loading) return <DashLoader />;
  const rate = data?.acceptance_rate ?? data?.acceptance_pct ?? 0;
  const avgAddons = data?.avg_addons_per_order ?? data?.average_addons ?? 0;
  const popularity = data?.popularity || data?.top_addons || [];
  const revenueSplit = data?.revenue_split || [];
  const pieData = revenueSplit.map((r) => ({ name: r.name || r.addon, value: r.revenue || r.amount || 0 }));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={Layers} label="Acceptance Rate" value={`${rate}%`} iconClass="text-success" iconBg="bg-success/15" />
        <StatTile icon={Layers} label="Avg Add-ons / Order" value={avgAddons} iconClass="text-primary" iconBg="bg-primary/10" />
      </div>
      <Card className="p-5">
        <SectionTitle icon={Layers} title="Add-on Popularity" />
        <HBarList data={popularity} valueKey="count" nameKey="name" formatValue={(v) => v} emptyTitle="No add-on data yet" />
      </Card>
      {pieData.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={DollarSign} title="Revenue Split by Add-on" />
          <SimplePie data={pieData} formatValue={formatNaira} />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 3. DELIVERY LOCATION — pie (on/off campus), bars (top hostels/gates), KPI
// ════════════════════════════════════════════════════════
export function DeliveryLocationDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.deliveryLocations());
  if (loading) return <DashLoader />;
  const onOff = data?.on_off_campus || data?.split || [];
  const pieData = onOff.map((d) => ({ name: d.label || d.type, value: d.count || d.value || 0 }));
  const hostels = data?.top_hostels || [];
  const gates = data?.top_gates || [];
  const feeTotal = data?.total_delivery_fees ?? data?.delivery_fee_total ?? 0;
  return (
    <div className="space-y-4">
      <StatTile icon={DollarSign} label="Total Delivery Fees" value={formatNaira(feeTotal)} iconClass="text-success" iconBg="bg-success/15" />
      {pieData.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={MapPin} title="On-Campus vs Off-Campus" />
          <SimplePie data={pieData} />
        </Card>
      )}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={MapPin} title="Top Hostels" />
          <HBarList data={hostels} valueKey="count" nameKey="name" emptyTitle="No hostel data yet" />
        </Card>
        <Card className="p-5">
          <SectionTitle icon={MapPin} title="Top Gates" />
          <HBarList data={gates} valueKey="count" nameKey="name" emptyTitle="No gate data yet" />
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 4. SQUAD ORDERS — pie, KPI, line, table, KPI
// ════════════════════════════════════════════════════════
export function SquadOrdersDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.squadOrders());
  if (loading) return <DashLoader />;
  const split = data?.squad_vs_individual || data?.split || [];
  const pieData = split.map((d) => ({ name: d.label || d.type, value: d.count || d.value || 0 }));
  const avgSize = data?.avg_squad_size ?? data?.average_squad_size ?? 0;
  const trend = data?.trend || [];
  const topSquads = data?.top_squads || [];
  const revenuePct = data?.squad_revenue_pct ?? data?.squad_revenue_percentage ?? 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={Users} label="Avg Squad Size" value={avgSize} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={DollarSign} label="Squad Revenue %" value={`${revenuePct}%`} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      {pieData.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Users} title="Squad vs Individual Orders" />
          <SimplePie data={pieData} />
        </Card>
      )}
      {trend.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={TrendingUp} title="Squad Order Trend" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="orders" stroke={COLORS[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {topSquads.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Users} title="Top Squads" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-muted-foreground text-xs border-b border-border">
                <th className="text-left py-2 font-extrabold">Squad</th>
                <th className="text-center py-2 font-extrabold">Orders</th>
                <th className="text-right py-2 font-extrabold">Revenue</th>
              </tr></thead>
              <tbody>
                {topSquads.slice(0, 10).map((s, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2 font-bold text-foreground">{s.name || s.squad_name}</td>
                    <td className="text-center py-2 text-muted-foreground">{s.orders || s.order_count || 0}</td>
                    <td className="text-right py-2 font-bold text-foreground">{formatNaira(s.revenue || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 5. DEMOGRAPHICS — bars (dept, faculty), stacked bar (level), pie, KPI
// ════════════════════════════════════════════════════════
export function DemographicsDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.demographics());
  if (loading) return <DashLoader />;
  const byDept = data?.by_department || data?.departments || [];
  const byFaculty = data?.by_faculty || data?.faculties || [];
  const byLevel = data?.by_academic_level || data?.by_level || [];
  const distribution = data?.customer_distribution || [];
  const avgSpend = data?.avg_spend_by_level ?? data?.average_spend ?? 0;
  const pieData = distribution.map((d) => ({ name: d.label || d.level, value: d.count || d.value || 0 }));
  return (
    <div className="space-y-4">
      <StatTile icon={DollarSign} label="Avg Spend by Level" value={formatNaira(avgSpend)} iconClass="text-primary" iconBg="bg-primary/10" />
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={GraduationCap} title="By Department" />
          <HBarList data={byDept} valueKey="count" nameKey="name" emptyTitle="No department data yet" />
        </Card>
        <Card className="p-5">
          <SectionTitle icon={GraduationCap} title="By Faculty" />
          <HBarList data={byFaculty} valueKey="count" nameKey="name" emptyTitle="No faculty data yet" />
        </Card>
      </div>
      {byLevel.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={GraduationCap} title="By Academic Level" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={byLevel} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="level" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>{byLevel.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {pieData.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Users} title="Customer Distribution" />
          <SimplePie data={pieData} />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 6. STUDENT ENGAGEMENT — histogram, lines, table, bar
// ════════════════════════════════════════════════════════
export function EngagementDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.engagement());
  if (loading) return <DashLoader />;
  const tiers = data?.engagement_tiers || data?.tiers || [];
  const hpTrend = data?.hp_earned_trend || data?.hp_trend || [];
  const checkinTrend = data?.checkins_trend || data?.checkin_trend || [];
  const topEngaged = data?.top_engaged || [];
  const byDept = data?.by_department || [];
  return (
    <div className="space-y-4">
      {tiers.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Activity} title="Engagement Tiers" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={tiers} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="tier" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>{tiers.map((d, i) => <Cell key={i} fill={TIER_COLORS[d.tier?.toLowerCase()] || COLORS[i % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      <div className="grid lg:grid-cols-2 gap-4">
        {hpTrend.length > 0 && (
          <Card className="p-5">
            <SectionTitle icon={Flame} title="HP Earned Trend" />
            <div className="h-48"><ResponsiveContainer width="100%" height="100%">
              <LineChart data={hpTrend} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="hp" stroke={COLORS[0]} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer></div>
          </Card>
        )}
        {checkinTrend.length > 0 && (
          <Card className="p-5">
            <SectionTitle icon={Activity} title="Check-ins Trend" />
            <div className="h-48"><ResponsiveContainer width="100%" height="100%">
              <LineChart data={checkinTrend} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="checkins" stroke={COLORS[1]} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer></div>
          </Card>
        )}
      </div>
      {topEngaged.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Users} title="Top Engaged Students" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-muted-foreground text-xs border-b border-border">
                <th className="text-left py-2 font-extrabold">Student</th>
                <th className="text-center py-2 font-extrabold">HP</th>
                <th className="text-center py-2 font-extrabold">Check-ins</th>
              </tr></thead>
              <tbody>
                {topEngaged.slice(0, 10).map((s, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2 font-bold text-foreground">{s.name || s.full_name || '—'}</td>
                    <td className="text-center py-2 text-muted-foreground">{s.hp || s.hp_balance || 0}</td>
                    <td className="text-center py-2 text-muted-foreground">{s.checkins || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {byDept.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={GraduationCap} title="Engagement by Department" />
          <HBarList data={byDept} valueKey="count" nameKey="name" emptyTitle="No data yet" />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 7. PAYMENT METHOD — pie, line, KPIs
// ════════════════════════════════════════════════════════
// Fixed four-category mapping. hp_or_free is its own slice — orders paid
// entirely with loyalty points or a discount (zero wallet/card movement) —
// and must never be filtered out or merged into the other three.
const PAYMENT_META = {
  wallet: { label: 'Wallet', color: '#E70E0E' },
  card: { label: 'Card', color: '#F2B84B' },
  split: { label: 'Split', color: '#6A1F00' },
  hp_or_free: { label: 'Points / Free', color: '#2E7D32' },
};

export function PaymentMethodDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.paymentMethods());
  if (loading) return <DashLoader />;
  // Accepts either an array of {method, count} entries or a keyed object
  // {wallet, card, split, hp_or_free} — normalize both to fixed slices.
  const raw = data?.split || data?.payment_methods || [];
  const entries = Array.isArray(raw)
    ? raw.map((d) => ({ key: String(d.method || d.label || '').toLowerCase(), value: d.count ?? d.value ?? 0 }))
    : Object.entries(raw || {}).map(([k, v]) => ({ key: String(k).toLowerCase(), value: Number(v) || 0 }));
  const pieData = Object.keys(PAYMENT_META)
    .map((k) => {
      const e = entries.find((x) => x.key === k || x.key.replace(/[-\s]/g, '_') === k);
      return { key: k, name: PAYMENT_META[k].label, value: e ? Number(e.value) || 0 : 0 };
    })
    .filter((d) => d.value > 0);
  const walletTrend = data?.wallet_trend || [];
  const avgBalance = data?.avg_wallet_balance ?? data?.average_wallet_balance ?? 0;
  const topupFreq = data?.topup_frequency ?? data?.top_up_frequency ?? '—';
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={CreditCard} label="Avg Wallet Balance" value={formatNaira(avgBalance)} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={CreditCard} label="Top-up Frequency" value={topupFreq} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      {pieData.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={CreditCard} title="Payment Method Split" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${value}`}>
                {pieData.map((d) => <Cell key={d.key} fill={PAYMENT_META[d.key].color} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {walletTrend.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={TrendingUp} title="Wallet Balance Trend" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <LineChart data={walletTrend} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} tickFormatter={(v) => `₦${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatNaira(v)} />
              <Line type="monotone" dataKey="balance" stroke={COLORS[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer></div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// 8. REVENUE — line (daily), stacked bar (by payment), KPIs, bar (day of week)
// ════════════════════════════════════════════════════════
export function RevenueDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.revenue());
  if (loading) return <DashLoader />;
  const daily = data?.daily_revenue || data?.daily || [];
  const byMethod = data?.by_payment_method || data?.revenue_by_method || [];
  const aov = data?.aov ?? data?.average_order_value ?? 0;
  const cumulative = data?.cumulative_total ?? data?.total_revenue ?? 0;
  const byDow = data?.by_day_of_week || data?.revenue_by_dow || [];
  // Build stacked bar data
  const methods = byMethod.length > 0 ? Object.keys(byMethod[0]).filter((k) => k !== 'date') : [];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={DollarSign} label="AOV" value={formatNaira(aov)} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={DollarSign} label="Cumulative Revenue" value={formatNaira(cumulative)} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      {daily.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={TrendingUp} title="Daily Revenue" />
          <div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <AreaChart data={daily} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <defs><linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS[0]} stopOpacity={0.3} />
                <stop offset="100%" stopColor={COLORS[0]} stopOpacity={0} />
              </linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} tickFormatter={(v) => `₦${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatNaira(v)} />
              <Area type="monotone" dataKey="revenue" stroke={COLORS[0]} strokeWidth={2} fill="url(#revGrad)" />
            </AreaChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {byMethod.length > 0 && methods.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={CreditCard} title="Revenue by Payment Method" />
          <div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={byMethod} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} tickFormatter={(v) => `₦${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatNaira(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {methods.map((m, i) => <Bar key={m} dataKey={m} stackId="a" fill={COLORS[i % COLORS.length]} />)}
            </BarChart>
          </ResponsiveContainer></div>
        </Card>
      )}
      {byDow.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={TrendingUp} title="Revenue by Day of Week" />
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={byDow} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} tickFormatter={(v) => `₦${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatNaira(v)} />
              <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>{byDow.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer></div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// HP ECOSYSTEM — enhanced with 4-tier pie (Ember/Flame/Blaze/Holy)
// ════════════════════════════════════════════════════════
export function HpEcosystemDashboard() {
  const { data, loading } = useDashboard(() => liveApi.admin.getAnalyticsHp());
  if (loading) return <DashLoader />;
  const inCirc = data?.hp_in_circulation ?? 0;
  const earned = data?.hp_earned_active ?? 0;
  const spent = data?.hp_spent ?? 0;
  const hpValue = data?.hp_value_naira ?? data?.hp_value ?? 0;
  const avgHp = data?.avg_hp_per_student ?? data?.avg_hp ?? 0;
  const tierDist = data?.tier_distribution || {};
  // Always show all 4 tiers — never drop Blaze/Inferno
  const pieData = ['ember', 'flame', 'blaze', 'holy'].map((t) => ({
    name: TIER_LABELS[t],
    value: tierDist[t] ?? tierDist[TIER_LABELS[t]] ?? 0,
  })).filter((d) => d.value > 0);
  const earnedVsSpent = [
    { name: 'Earned', value: earned },
    { name: 'Spent', value: spent },
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Flame} label="HP in Circulation" value={inCirc.toLocaleString()} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={DollarSign} label="HP Value (₦)" value={formatNaira(hpValue)} iconClass="text-success" iconBg="bg-success/15" />
        <StatTile icon={Users} label="Avg HP / Student" value={avgHp.toLocaleString()} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
        <StatTile icon={Flame} label="Redemption Rate" value={`${data?.redemption_rate ?? 0}%`} iconClass="text-destructive" iconBg="bg-destructive/10" />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionTitle icon={Flame} title="Earned vs Spent" />
          {earned > 0 || spent > 0 ? (
            <div className="h-56"><ResponsiveContainer width="100%" height="100%">
              <BarChart data={earnedVsSpent} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}><Cell fill={COLORS[0]} /><Cell fill={COLORS[1]} /></Bar>
              </BarChart>
            </ResponsiveContainer></div>
          ) : <EmptyState icon={Flame} title="No HP data yet" />}
        </Card>
        <Card className="p-5">
          <SectionTitle icon={Flame} title="Tier Distribution (4 tiers)" />
          {pieData.length > 0 ? (
            <div className="h-56"><ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${value}`}>
                  {pieData.map((d, i) => <Cell key={i} fill={TIER_COLORS[['ember', 'flame', 'blaze', 'holy'][i]] || COLORS[i]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer></div>
          ) : <EmptyState icon={Flame} title="No tier data yet" />}
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════
// B1. ACADEMIC CALENDAR — order volume during exam/semester periods vs normal days
// ════════════════════════════════════════════════════════
export function AcademicCalendarDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.academicCalendar());
  if (loading) return <DashLoader />;
  const periods = data?.academic_periods || [];
  const baseline = data?.normal_day_baseline || {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatTile icon={CalendarDays} label="Academic Periods" value={periods.length} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={TrendingUp} label="Normal-Day Avg Orders" value={`${baseline.avg_orders_per_day ?? '—'}/day`} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
        <StatTile icon={DollarSign} label="Normal-Day Avg Revenue" value={formatNaira(baseline.avg_revenue_per_day ?? 0)} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      {periods.length > 0 ? (
        <Card className="p-5">
          <SectionTitle icon={CalendarDays} title="Orders by Academic Period" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[480px]">
              <thead>
                <tr className="text-muted-foreground text-xs border-b border-border">
                  <th className="text-left py-2 font-extrabold">Period</th>
                  <th className="text-left py-2 font-extrabold">Type</th>
                  <th className="text-center py-2 font-extrabold">Orders</th>
                  <th className="text-right py-2 font-extrabold">Revenue</th>
                  <th className="text-right py-2 font-extrabold">Avg/Day</th>
                </tr>
              </thead>
              <tbody>
                {periods.map((p, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2.5 font-bold text-foreground">{p.name || '—'}</td>
                    <td className="py-2.5 text-muted-foreground capitalize">{(p.period_type || '').replace(/_/g, ' ')}</td>
                    <td className="text-center py-2.5 text-muted-foreground font-extrabold">{p.total_orders ?? 0}</td>
                    <td className="text-right py-2.5 font-bold text-foreground">{formatNaira(p.total_revenue ?? 0)}</td>
                    <td className="text-right py-2.5 text-accent-foreground font-extrabold">{p.avg_orders_per_day ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <Card className="p-6"><EmptyState icon={CalendarDays} title="No academic calendar data yet" body="Add academic periods in Config → Academic Calendar to see trends here." /></Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// B2. ORDER SOURCES — breakdown by channel (website, whatsapp, instagram, etc.)
// ════════════════════════════════════════════════════════
export function OrderSourcesDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.orderSources());
  if (loading) return <DashLoader />;
  const sources = data?.order_sources || [];
  const total = data?.total_orders ?? 0;
  const pieData = sources.map((s) => ({ name: s.order_source || 'unspecified', value: s.count || 0 }));
  return (
    <div className="space-y-4">
      <StatTile icon={Radio} label="Total Orders" value={total} iconClass="text-primary" iconBg="bg-primary/10" />
      {pieData.length > 0 ? (
        <Card className="p-5">
          <SectionTitle icon={Radio} title="Orders by Channel" />
          <SimplePie data={pieData} />
        </Card>
      ) : (
        <Card className="p-6"><EmptyState icon={Radio} title="No order source data yet" body="Channels appear once orders are placed." /></Card>
      )}
      {sources.length > 0 && (
        <Card className="p-5">
          <SectionTitle icon={Radio} title="Channel Breakdown" />
          <HBarList data={sources.map((s) => ({ name: s.order_source || 'unspecified', value: s.count || 0, revenue: s.revenue || 0 }))} valueKey="value" nameKey="name" formatValue={(v) => v} emptyTitle="No data yet" />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// A9. REFERRAL NETWORK — top referrers driving new signups
// ════════════════════════════════════════════════════════
export function ReferralNetworkDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.referralNetwork());
  if (loading) return <DashLoader />;
  const total = data?.total_referrals ?? 0;
  const completed = data?.completed_referrals ?? 0;
  const topReferrers = data?.top_referrers || [];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={Share2} label="Total Referrals" value={total} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={Share2} label="Completed" value={completed} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      {topReferrers.length > 0 ? (
        <Card className="p-5">
          <SectionTitle icon={Share2} title="Top Referrers" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground text-xs border-b border-border">
                  <th className="text-left py-2 font-extrabold">Referrer</th>
                  <th className="text-center py-2 font-extrabold">Referrals</th>
                  <th className="text-center py-2 font-extrabold">HP Earned</th>
                </tr>
              </thead>
              <tbody>
                {topReferrers.map((r, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    <td className="py-2.5 font-bold text-foreground">{r.name || r.referrer_id}</td>
                    <td className="text-center py-2.5 text-muted-foreground font-extrabold">{r.referral_count ?? 0}</td>
                    <td className="text-center py-2.5 text-accent-foreground font-extrabold">{(r.hp_earned ?? 0).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <Card className="p-6"><EmptyState icon={Share2} title="No referral network data yet" body="Top referrers appear once referrals start converting." /></Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════
// A8. RETENTION & LTV — repeat order rate and customer lifetime value
// ════════════════════════════════════════════════════════
export function RetentionLtvDashboard() {
  const { data, loading } = useDashboard(() => liveApi.analytics.retentionLtv());
  if (loading) return <DashLoader />;
  const totalStudents = data?.total_students ?? 0;
  const orderingCustomers = data?.ordering_customers ?? 0;
  const repeatCustomers = data?.repeat_customers ?? 0;
  const repeatRate = data?.repeat_customer_rate ?? 0;
  const ltv = data?.customer_ltv ?? 0;
  const arpu = data?.arpu ?? 0;
  const totalRevenue = data?.total_revenue ?? 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Users} label="Total Students" value={totalStudents.toLocaleString()} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={Repeat} label="Repeat Customers" value={repeatCustomers.toLocaleString()} iconClass="text-accent-foreground" iconBg="bg-accent/25" />
        <StatTile icon={Repeat} label="Repeat Rate" value={`${repeatRate}%`} iconClass="text-success" iconBg="bg-success/15" />
        <StatTile icon={DollarSign} label="Customer LTV" value={formatNaira(ltv)} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <StatTile icon={DollarSign} label="ARPU (all students)" value={formatNaira(arpu)} iconClass="text-primary" iconBg="bg-primary/10" />
        <StatTile icon={DollarSign} label="Total Revenue (delivered)" value={formatNaira(totalRevenue)} iconClass="text-success" iconBg="bg-success/15" />
      </div>
      <Card className="p-5">
        <SectionTitle icon={Repeat} title="Ordering vs Repeat Customers" />
        {orderingCustomers > 0 ? (
          <div className="h-56"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={[{ name: 'One-time', value: orderingCustomers - repeatCustomers }, { name: 'Repeat', value: repeatCustomers }]} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(36 35% 82%)" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(18 30% 35%)' }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}><Cell fill={COLORS[0]} /><Cell fill={COLORS[1]} /></Bar>
            </BarChart>
          </ResponsiveContainer></div>
        ) : <EmptyState icon={Repeat} title="No retention data yet" />}
      </Card>
    </div>
  );
}