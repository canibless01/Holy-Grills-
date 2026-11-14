import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDownLeft, ArrowRightLeft, CalendarClock, Download, RefreshCw, Repeat2, Users, Wallet } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { liveApi } from '@/lib/liveApi';
import { formatWalletMoney } from '@/lib/hgUtils';
import { watDateKey } from '@/lib/watCalendar';
import { csvCell } from '@/lib/csvCell';
import { Card, Skeleton, StatTile } from './ui/AdminKit';

const money = (value: number) => formatWalletMoney(value);
const count = (value: number) => value.toLocaleString('en-NG');
const shiftDay = (day: string, delta: number) => {
  const value = new Date(day + 'T00:00:00Z'); value.setUTCDate(value.getUTCDate() + delta);
  return value.toISOString().slice(0, 10);
};
const dayLabel = (day: string) => new Date(day + 'T00:00:00Z').toLocaleDateString('en-NG', { day: 'numeric', month: 'short', timeZone: 'UTC' });

function checkedReport(value: any) {
  const numeric = (section, keys) => section && keys.every(key => typeof section[key] === 'number' && Number.isFinite(section[key]));
  if (!value || !Number.isFinite(Date.parse(value.as_of)) || value.currency !== 'NGN' || !value.period?.from_date || !value.period?.to_date ||
      !numeric(value.balances, ['outstanding', 'wallet_accounts', 'funded_accounts', 'inactive_balance', 'average_funded_balance', 'balance_issues']) ||
      !numeric(value.activity, ['funding_received', 'automatic_received', 'automatic_contributions', 'manual_funding_received', 'refunds_credited', 'other_credits', 'wallet_debits', 'adjustments']) ||
      !numeric(value.transfers, ['count', 'volume']) || !numeric(value.automatic_funding, ['plans', 'owners', 'lifetime_credited', 'lifetime_contributions']) ||
      !numeric(value.automatic_funding.states, ['active', 'draft', 'attention', 'stopped', 'completed']) ||
      !numeric(value.payment_health, ['awaiting_first_payment', 'awaiting_confirmation', 'unconfirmed_amount', 'failed_in_period']) ||
      !numeric(value.projection, ['eligible_plans', 'excluded_active_plans', 'overdue_plans']) ||
      !Array.isArray(value.projection.horizons) || value.projection.horizons.length !== 3 ||
      !value.projection.horizons.every(h => numeric(h, ['days', 'amount', 'contributions']) && h.through_date) ||
      !Array.isArray(value.projection.daily) || !value.projection.daily.every(day => numeric(day, ['amount', 'contributions']) && Number.isFinite(Date.parse(day.date))) ||
      !Array.isArray(value.daily_history) || !value.daily_history.every(day => numeric(day, ['manual_funding', 'automatic_funding', 'refunds', 'wallet_debits']) && Number.isFinite(Date.parse(day.date)))) {
    throw new Error('The wallet report was incomplete. Please retry.');
  }
  return value;
}

export default function AdminWalletAnalytics() {
  const { adminCampusId } = useCampus();
  const { user } = useHolyGrill();
  const campus = user?.role === 'super_admin' ? adminCampusId : user?.campus_id || user?.profile?.campus_id;
  return <WalletFundingWorkspace key={campus || 'global'} campus={campus} />;
}

function WalletFundingWorkspace({ campus }) {
  const [range, setRange] = useState(() => ({ from: shiftDay(watDateKey(), -29), to: watDateKey() }));
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current; setLoading(true); setError('');
    try {
      const result = checkedReport(await liveApi.analytics.wallet({ from_date: range.from, to_date: range.to, ...(campus ? { campus_id: campus } : {}) }));
      if (current === generation.current) setReport(result);
    } catch (err) {
      if (current === generation.current) setError(err?.message || 'Wallet analytics could not be loaded. Please try again.');
    } finally { if (current === generation.current) setLoading(false); }
  }, [campus, range.from, range.to]);
  useEffect(() => { void load(); return () => { generation.current++; }; }, [load]);

  const apply = (event) => {
    event.preventDefault();
    if (from === range.from && to === range.to) void load(); else setRange({ from, to });
  };
  const preset = (days: number) => {
    const next = { from: shiftDay(watDateKey(), 1 - days), to: watDateKey() };
    setFrom(next.from); setTo(next.to); setRange(next);
  };
  const download = () => {
    if (!report) return;
    const rows: unknown[][] = [['Section', 'Metric / date', 'Amount (NGN)', 'Count', 'As of (UTC)']];
    rows.push(['Snapshot', 'Outstanding customer wallet credit', report.balances.outstanding, report.balances.funded_accounts, report.as_of]);
    rows.push(['Period', `${report.period.from_date} through ${report.period.to_date} (WAT)`, '', '', report.as_of]);
    rows.push(['Scope', report.campus_id || 'All campuses', '', '', report.as_of]);
    for (const [metric, value] of Object.entries(report.activity)) {
      const isCount = metric === 'automatic_contributions' || metric === 'adjustments';
      rows.push(['Selected period', metric, isCount ? '' : value, isCount ? value : '', report.as_of]);
    }
    rows.push(['Selected period', 'Transfers (once per transfer)', report.transfers.volume, report.transfers.count, report.as_of]);
    for (const h of report.projection.horizons) rows.push(['Projection', `Through ${h.through_date}`, h.amount, h.contributions, report.as_of]);
    for (const day of report.daily_history) {
      rows.push(['Manual funding', day.date, day.manual_funding, '', report.as_of]);
      rows.push(['Automatic funding', day.date, day.automatic_funding, '', report.as_of]);
    }
    for (const day of report.projection.daily) rows.push(['Projected wallet credits', day.date, day.amount, day.contributions, report.as_of]);
    rows.push(['Policy', 'Super-admin accounts excluded; projections are estimates', '', '', report.as_of]);
    const csv = rows.map(row => row.map(value => `"${csvCell(value)}"`).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `wallet-funding_${report.period.from_date}_${report.period.to_date}.csv`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const states = report?.automatic_funding.states;
  return <div className="min-w-0 space-y-5">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div><h2 className="font-heading text-xl font-extrabold">Wallet &amp; Funding</h2><p className="mt-1 text-sm text-muted-foreground">Customer wallet credit and automatic contributions.</p><p className="mt-1 text-xs font-semibold text-primary">Super-admin accounts are excluded throughout this report.</p></div>
      <Link to="/admin?section=wallet" className="shrink-0 rounded-xl border border-border px-3 py-2 text-xs font-bold text-primary">View wallet transactions</Link>
    </div>
    <Card className="space-y-3 p-4">
      <form onSubmit={apply} className="grid grid-cols-2 items-end gap-3 sm:grid-cols-[1fr_1fr_auto_auto]">
        <label className="min-w-0 text-xs font-bold">From date<input aria-label="Funding from date" className="mt-1 w-full min-w-0 rounded-xl border border-border bg-background p-2.5 text-sm" type="date" required value={from} min={to ? shiftDay(to, -365) : undefined} max={to || undefined} onChange={e => setFrom(e.target.value)} /></label>
        <label className="min-w-0 text-xs font-bold">To date<input aria-label="Funding to date" className="mt-1 w-full min-w-0 rounded-xl border border-border bg-background p-2.5 text-sm" type="date" required value={to} min={from || undefined} onChange={e => setTo(e.target.value)} /></label>
        <button disabled={loading} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">Apply dates</button>
        <button type="button" disabled={loading} onClick={load} className="flex items-center justify-center gap-1.5 rounded-xl border border-border px-3 py-2.5 text-sm font-bold disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Refresh</button>
      </form>
      <div className="flex flex-wrap items-center gap-2">{[7, 30, 90].map(days => <button key={days} disabled={loading} onClick={() => preset(days)} className="rounded-full bg-secondary px-3 py-1.5 text-xs font-bold disabled:opacity-50">Last {days} days</button>)}<span className="text-xs text-muted-foreground">WAT dates · up to 366 days</span></div>
    </Card>
    {error && <Card role="alert" className="space-y-2 border-destructive/40 p-4"><p className="text-sm text-destructive">{error}</p>{report && <p className="text-xs text-muted-foreground">Showing the previous snapshot below. These values have not refreshed.</p>}<button disabled={loading} onClick={load} className="text-sm font-bold text-primary underline">Retry wallet report</button></Card>}
    {!report && loading && <div role="status" aria-label="Loading wallet analytics" className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-28" />)}</div>}
    {report && <>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>Snapshot: {new Date(report.as_of).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })} WAT{loading ? ' · Updating…' : ''}</span><button onClick={download} className="flex items-center gap-1.5 font-bold text-primary"><Download className="h-3.5 w-3.5" />Download report</button></div>
      {report.balances.balance_issues > 0 && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{count(report.balances.balance_issues)} wallets need reconciliation. Invalid or non-NGN balances are excluded from the total.</p>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile icon={Wallet} label="Outstanding wallet credit" value={<span className="break-all tabular-nums">{money(report.balances.outstanding)}</span>} sub="Current customer balances" />
        <StatTile icon={Users} label="Customers with funds" value={count(report.balances.funded_accounts)} sub={`${count(report.balances.wallet_accounts)} wallet accounts`} />
        <StatTile icon={Repeat2} label="Active funding plans" value={count(states.active)} sub={`${count(report.projection.eligible_plans)} eligible for projection`} />
        <StatTile icon={ArrowDownLeft} label="Confirmed funding" value={<span className="break-all tabular-nums">{money(report.activity.funding_received)}</span>} sub="Selected dates · manual + automatic" />
      </div>
      <Card className="p-4 text-xs leading-relaxed text-muted-foreground">Wallet credit is available for customers to spend. It includes refunds and other credits, so it is different from sales revenue or cash in the bank. Balances are current; funding activity uses the selected dates.</Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-4 p-4 sm:p-5"><div><h3 className="font-heading font-bold">Automatic funding</h3><p className="mt-1 text-xs text-muted-foreground">{dayLabel(report.period.from_date)} – {dayLabel(report.period.to_date)}</p></div>
          <div className="rounded-2xl bg-success/10 p-4"><p className="text-xs text-muted-foreground">Confirmed automatic wallet credits</p><p className="mt-1 text-2xl font-extrabold text-success">{money(report.activity.automatic_received)}</p><p className="mt-1 text-xs">{count(report.activity.automatic_contributions)} successful contributions · included in confirmed funding</p></div>
          <dl className="space-y-2 text-sm"><Row label="All-time automatic credits" value={money(report.automatic_funding.lifetime_credited)} /><Row label="All-time successful contributions" value={count(report.automatic_funding.lifetime_contributions)} /><Row label="People with a plan" value={count(report.automatic_funding.owners)} /></dl>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{([['active','Active'],['draft','Awaiting setup'],['attention','Needs attention'],['stopped','Stopped'],['completed','Completed']] as const).map(([key,label]) => <div key={key} className="rounded-xl bg-background p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-bold">{count(states[key])}</p></div>)}</div>
        </Card>
        <Card className="space-y-4 p-4 sm:p-5"><h3 className="font-heading font-bold">Wallet activity</h3><dl className="space-y-3 text-sm"><Row label="Manual card / bank funding" value={money(report.activity.manual_funding_received)} /><Row label="Refunds credited" value={money(report.activity.refunds_credited)} /><Row label="Other wallet credits" value={money(report.activity.other_credits)} /><Row label="Wallet debits, excluding transfers" value={money(report.activity.wallet_debits)} /><Row label="Internal transfer volume" value={money(report.transfers.volume)} /><Row label="Internal transfers" value={count(report.transfers.count)} /><Row label="Credit held by inactive accounts" value={money(report.balances.inactive_balance)} /><Row label="Average funded-wallet balance" value={money(report.balances.average_funded_balance)} /></dl><p className="text-xs leading-relaxed text-muted-foreground">Transfers between included accounts are counted once and do not add new funding to the ecosystem.</p></Card>
      </div>
      <Card className="space-y-3 p-4 sm:p-5"><h3 className="font-heading font-bold">Confirmed funding by day</h3><p className="text-xs text-muted-foreground">Actual wallet credits for the selected WAT dates. Automatic and manual funding are separate parts of the total.</p><div className="h-60 min-w-0" aria-label="Daily confirmed funding chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={report.daily_history}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tickFormatter={dayLabel} minTickGap={28} fontSize={10} /><YAxis width={56} fontSize={10} /><Tooltip labelFormatter={dayLabel} formatter={(value: number, name) => [money(value), name]} /><Bar dataKey="manual_funding" name="Manual funding" stackId="funding" fill="#F2B84B" /><Bar dataKey="automatic_funding" name="Automatic funding" stackId="funding" fill="#E70E0E" radius={[3,3,0,0]} /></BarChart></ResponsiveContainer></div><div className="flex gap-4 text-xs"><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-[#F2B84B]" />Manual funding</span><span className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-primary" />Automatic funding</span></div></Card>
      <Card className="space-y-4 p-4 sm:p-5"><div className="flex items-center gap-2"><CalendarClock className="h-5 w-5 text-primary" /><h3 className="font-heading font-bold">Projected wallet contributions</h3></div><p className="text-xs leading-relaxed text-muted-foreground">Estimates from eligible active plans, assuming payments succeed. Includes the rest of today. Contribution limits and end dates are respected; overdue plans count once without catch-up charges. Unpaid, paused, stopped and unconfirmed plans are excluded.</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{report.projection.horizons.map(h => <div key={h.days} className="rounded-2xl border border-border bg-background p-4"><p className="text-xs font-bold text-muted-foreground">Next {h.days} days</p><p className="mt-1 text-xl font-extrabold">{money(h.amount)}</p><p className="mt-1 text-xs">{count(h.contributions)} contributions</p><p className="mt-1 text-[11px] text-muted-foreground">Through {dayLabel(h.through_date)}</p></div>)}</div>
        <p className="text-xs text-muted-foreground">{count(report.projection.excluded_active_plans)} active plans excluded from the estimate · {count(report.projection.overdue_plans)} eligible plans currently overdue</p>
        <details className="rounded-xl border border-border p-3"><summary className="cursor-pointer text-sm font-bold">Daily projection · next 30 days</summary><div className="mt-3 max-h-72 overflow-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-border"><th className="py-2">WAT date</th><th className="py-2 text-right">Contributions</th><th className="py-2 text-right">Projected credit</th></tr></thead><tbody>{report.projection.daily.map(day => <tr key={day.date} className="border-b border-border/50"><td className="py-2">{dayLabel(day.date)}</td><td className="py-2 text-right">{count(day.contributions)}</td><td className="py-2 text-right font-semibold">{money(day.amount)}</td></tr>)}</tbody></table></div></details>
      </Card>
      <Card className="space-y-3 p-4 sm:p-5"><div className="flex items-center gap-2"><ArrowRightLeft className="h-4 w-4 text-primary" /><h3 className="font-heading font-bold">Payment health</h3></div><dl className="grid gap-3 text-sm sm:grid-cols-2"><Row label="Plans awaiting first payment" value={count(report.payment_health.awaiting_first_payment)} /><Row label="Contributions awaiting confirmation" value={count(report.payment_health.awaiting_confirmation)} /><Row label="Unconfirmed contribution value" value={money(report.payment_health.unconfirmed_amount)} /><Row label="Failed payments in selected dates" value={count(report.payment_health.failed_in_period)} /></dl><p className="text-xs text-muted-foreground">Unconfirmed contributions are separate from confirmed receipts and projections.</p></Card>
    </>}
  </div>;
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex items-start justify-between gap-3"><dt className="min-w-0 text-muted-foreground">{label}</dt><dd className="max-w-[55%] shrink-0 break-all text-right font-bold tabular-nums">{value}</dd></div>;
}
