import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import {
  Coins, RefreshCw, Calendar, TrendingDown, TrendingUp, CircleDollarSign, Gift, AlertCircle,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { Card, Skeleton, EmptyState, SectionTitle, StatTile, body } from './ui/AdminKit';

const FLAME = ['#E70E0E', '#F2B84B', '#FF9500', '#6A1F00', '#A8301A', '#C47B3A'];

const todayStr = () => new Date().toISOString().slice(0, 10);
const daysAgoStr = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };

const num = (v) => (v == null || isNaN(Number(v)) ? 0 : Number(v));
const pct = (v, digits = 1) => `${(num(v) * 100).toFixed(digits)}%`;

// HP Economics — Stage 16 admin reporting dashboard.
// Three sections, one shared date-range picker all three respect:
//   1. Programme Overview (metrics grid + liability vs cost + efficiency)
//   2. Tier Breakdown (plain table)
//   3. Redemption Analytics (cost-by-type donut + totals)
// Endpoints: GET /admin/economics/overview | /tier-breakdown | /redemption-analytics.
export default function AdminEconomics() {
  const [fromDate, setFromDate] = useState(daysAgoStr(30));
  const [toDate, setToDate] = useState(todayStr());
  const [overview, setOverview] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [redemption, setRedemption] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = async () => {
    setLoading(true); setFailed(false);
    // Backend reads start_date / end_date (admin_economics.py). Sending
    // from_date/to_date silently dropped the filter.
    const params = { start_date: fromDate, end_date: toDate };
    const [ov, tb, rd] = await Promise.allSettled([
      liveApi.admin.getEconomicsOverview(params),
      liveApi.admin.getEconomicsTierBreakdown(params),
      liveApi.admin.getEconomicsRedemptionAnalytics(params),
    ]);
    if (ov.status === 'fulfilled') setOverview(body(ov.value)); else setOverview(null);
    if (tb.status === 'fulfilled') {
      const t = body(tb.value);
      setTiers(Array.isArray(t) ? t : (t?.tiers || t?.breakdown || []));
    } else setTiers([]);
    setRedemption(rd.status === 'fulfilled' ? body(rd.value) : null);
    setFailed(ov.status === 'rejected' && tb.status === 'rejected' && rd.status === 'rejected');
    setLoading(false);
  };

  useEffect(() => { load(); }, [fromDate, toDate]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20" />
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (failed) {
    return (
      <Card>
        <EmptyState
          icon={AlertCircle}
          title="Economics data unavailable"
          body="The HP economics endpoints didn't respond. Check your admin session and retry."
          action={
            <button onClick={load} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          }
        />
      </Card>
    );
  }

  const effPct = Math.round(num(overview?.programme_efficiency) * 100);
  const effClass = effPct < 85 ? 'text-success' : effPct <= 100 ? 'text-accent-foreground' : 'text-destructive';
  const variancePts = (num(overview?.variance_from_target) * 100).toFixed(1);

  const metrics = [
    { label: 'Food Revenue', value: formatNaira(num(overview?.food_revenue)), icon: Coins, iconClass: 'text-success', iconBg: 'bg-success/15' },
    { label: 'HP Issued', value: num(overview?.hp_issued).toLocaleString(), icon: TrendingUp, iconClass: 'text-primary', iconBg: 'bg-primary/10' },
    { label: 'Pending HP', value: num(overview?.pending_hp).toLocaleString(), icon: Calendar, iconClass: 'text-accent-foreground', iconBg: 'bg-accent/25' },
    { label: 'Active HP', value: num(overview?.active_hp).toLocaleString(), icon: Coins, iconClass: 'text-primary', iconBg: 'bg-primary/10' },
    { label: 'HP Redeemed', value: num(overview?.hp_redeemed).toLocaleString(), icon: Gift, iconClass: 'text-success', iconBg: 'bg-success/15' },
    { label: 'HP Outstanding', value: num(overview?.hp_outstanding).toLocaleString(), icon: TrendingDown, iconClass: 'text-destructive', iconBg: 'bg-destructive/10' },
  ];

  const costByType = Object.entries(redemption?.cost_by_type || {})
    .filter(([, v]) => v != null && typeof v !== 'object')
    .map(([name, value], i) => ({ name: name.replace(/_/g, ' '), value: num(value), fill: FLAME[i % FLAME.length] }));
  const totalCost = num(redemption?.total_actual_cost);
  const perHp = num(redemption?.actual_cost_per_redeemed_hp);

  return (
    <div className="space-y-4">
      {/* Date-range picker — all three sections respect it */}
      <Card className="p-4 flex flex-col lg:flex-row lg:items-center gap-3">
        <div className="flex items-center gap-2 text-sm font-extrabold text-foreground shrink-0">
          <Coins className="w-4 h-4 text-primary" /> HP Economics
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">From</label>
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="w-full mt-0.5 px-3 py-2 rounded-xl border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div className="flex-1">
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">To</label>
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="w-full mt-0.5 px-3 py-2 rounded-xl border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary active:scale-95 transition shrink-0 lg:ml-auto">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </Card>

      {/* 1. Programme Overview */}
      <Card className="p-5">
        <SectionTitle icon={Coins} title="Programme Overview" sub={`${fromDate} → ${toDate} · GET /admin/economics/overview`} />
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {metrics.map((m, i) => (
            <motion.div key={m.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04, duration: 0.3 }}>
              <StatTile {...m} />
            </motion.div>
          ))}
        </div>

        {/* Comparison panel — the read-from-across-the-room number */}
        <div className="mt-4 rounded-2xl bg-gradient-dark p-5 text-white shadow-card">
          <div className="grid sm:grid-cols-2 gap-3">
            <div className="rounded-xl bg-white/10 border border-white/20 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-wider text-white/60">Theoretical Liability</div>
              <div className="font-heading font-extrabold text-xl mt-1">{formatNaira(num(overview?.theoretical_liability))}</div>
              <div className="text-[11px] text-white/60 mt-0.5">If every outstanding HP were redeemed</div>
            </div>
            <div className="rounded-xl bg-white/10 border border-white/20 p-4">
              <div className="text-[10px] font-extrabold uppercase tracking-wider text-white/60">Actual Redemption Cost</div>
              <div className="font-heading font-extrabold text-xl mt-1 text-accent">{formatNaira(num(overview?.actual_redemption_cost))}</div>
              <div className="text-[11px] text-white/60 mt-0.5">Really spent on redemptions</div>
            </div>
          </div>
          <div className="text-center py-5">
            <div className="text-[10px] font-extrabold uppercase tracking-widest text-white/60">Programme Efficiency</div>
            <motion.div
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', stiffness: 200, damping: 18 }}
              className={`font-heading font-black text-5xl sm:text-6xl mt-1 ${effClass}`}
            >
              {effPct}%
            </motion.div>
            <div className="text-xs text-white/70 mt-1">
              Actual {pct(overview?.actual_programme_cost_pct, 2)} vs target {pct(overview?.target_programme_cost_pct)} · variance {variancePts} pts
            </div>
          </div>
        </div>
      </Card>

      {/* 2. Tier Breakdown */}
      <Card className="p-5">
        <SectionTitle icon={Coins} title="Tier Breakdown" sub="One row per tier — scan for the outlier" />
        {tiers.length === 0 ? (
          <EmptyState icon={Coins} title="No tier data yet" body="A freshly launched campus starts at ₦0 — tiers appear as HP flows." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="text-muted-foreground text-[11px] uppercase tracking-wide border-b border-border">
                  <th className="text-left py-2.5 font-extrabold">Tier</th>
                  <th className="text-right py-2.5 font-extrabold">Revenue</th>
                  <th className="text-right py-2.5 font-extrabold">HP Issued</th>
                  <th className="text-right py-2.5 font-extrabold">HP Redeemed</th>
                  <th className="text-right py-2.5 font-extrabold">Actual Cost</th>
                  <th className="text-right py-2.5 font-extrabold">Effective %</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map((t, i) => (
                  <motion.tr key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.05, 0.3) }} className="border-b border-border/60 last:border-0 hover:bg-secondary/40 transition-colors">
                    <td className="py-2.5 font-extrabold text-foreground capitalize">{t.tier || '—'}</td>
                    <td className="text-right py-2.5 font-bold text-foreground">{formatNaira(num(t.revenue))}</td>
                    <td className="text-right py-2.5 font-bold text-foreground">{num(t.hp_issued).toLocaleString()}</td>
                    <td className="text-right py-2.5 font-bold text-foreground">{num(t.hp_redeemed).toLocaleString()}</td>
                    <td className="text-right py-2.5 font-bold text-foreground">{formatNaira(num(t.actual_cost))}</td>
                    <td className="text-right py-2.5 font-extrabold text-primary">{pct(t.effective_pct, 2)}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 3. Redemption Analytics */}
      <Card className="p-5">
        <SectionTitle icon={CircleDollarSign} title="Redemption Analytics" sub="Where redemption cost actually goes" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 items-center">
          <div className="h-52">
            {costByType.length === 0 ? (
              <EmptyState icon={Gift} title="No redemptions yet" body="Cost-by-type fills in after the first redemptions." />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={costByType} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={42} outerRadius={72} paddingAngle={2}>
                    {costByType.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12, border: '1px solid hsl(36 35% 82%)' }} formatter={(v) => formatNaira(v)} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <StatTile icon={Coins} label="Total Actual Cost" value={formatNaira(totalCost)} iconClass="text-primary" iconBg="bg-primary/10" />
          <StatTile icon={TrendingDown} label="Cost per Redeemed HP" value={formatNaira(perHp)} sub="Actual cost ÷ HP redeemed" iconClass="text-success" iconBg="bg-success/15" />
        </div>
        {costByType.length > 0 && (
          <div className="flex flex-wrap gap-3 mt-3">
            {costByType.map((c) => (
              <div key={c.name} className="flex items-center gap-1.5 text-xs">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c.fill }} />
                <span className="capitalize text-muted-foreground">{c.name}</span>
                <span className="font-extrabold text-foreground">{formatNaira(c.value)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}