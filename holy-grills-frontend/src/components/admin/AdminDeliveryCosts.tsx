import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Download, History, RefreshCw, Truck } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { Modal, Field, TextInput } from './AdminShared';

const naira = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = value => naira.format(Number(value ?? 0));
const watDay = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const monthStart = () => `${watDay().slice(0, 8)}01`;
const inputClass = 'rounded-xl border border-border bg-card p-2.5 text-sm';
const buttonClass = 'rounded-full border border-border px-4 py-2 text-sm font-bold disabled:opacity-50';
const csvCell = value => {
  let text = value == null ? '' : String(value);
  if (typeof value === 'string' && /^[\s]*[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
};

function BalanceTrend({ points }) {
  const values = points.map(point => Number(point.balance));
  const low = Math.min(0, ...values), high = Math.max(0, ...values), range = high - low || 1;
  const y = amount => 110 - ((amount - low) / range) * 90;
  const line = values.map((v, i) => `${20 + i * 560 / Math.max(1, values.length - 1)},${y(v)}`).join(' ');
  return <div className="rounded-2xl border border-border bg-card p-4">
    <h3 className="font-bold">Reconciled pool balance over time</h3>
    <p className="text-xs text-muted-foreground">Refunds and cost corrections appear when recorded. WAT dates.</p>
    <svg viewBox="0 0 600 140" role="img" aria-label={`Pool balance from ${points[0]?.day || ''} to ${points.at(-1)?.day || ''}; closing balance ${money(values.at(-1))}`} className="mt-3 w-full max-h-48">
      <line x1="20" x2="580" y1={y(0)} y2={y(0)} stroke="currentColor" opacity="0.2" />
      <text x="20" y="12" fontSize="10" fill="currentColor">{money(high)}</text>
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="3" className="text-primary" />
      {values.map((value, index) => <circle key={index} cx={20 + index * 560 / Math.max(1, values.length - 1)} cy={y(value)} r={values.length === 1 ? 4 : 1.5} fill="currentColor" className="text-primary" />)}
      <text x="20" y="135" fontSize="11" fill="currentColor">{points[0]?.day}</text><text x="580" y="135" textAnchor="end" fontSize="11" fill="currentColor">{points.at(-1)?.day}</text>
    </svg>
    <details className="text-xs"><summary className="cursor-pointer font-semibold">View daily figures</summary><div className="mt-2 max-h-44 overflow-auto">{points.map(point => <div key={point.day} className="flex justify-between border-b border-border py-1"><span>{point.day}</span><span>{money(point.balance)} · change {money(point.change)}</span></div>)}</div></details>
  </div>;
}

export default function AdminDeliveryCosts() {
  const { adminCampusId } = useCampus();
  const { user } = useHolyGrill();
  const campus = user?.role === 'super_admin' ? adminCampusId : user?.campus_id || user?.profile?.campus_id;
  const scope = campus || '';
  const [day, setDay] = useState(watDay);
  const [from, setFrom] = useState(monthStart);
  const [to, setTo] = useState(watDay);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState(null);
  const [floor, setFloor] = useState('');
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const busy = useRef(false);
  const generation = useRef(0);
  const viewKey = `${scope}:${day}:${from}:${to}`;
  const visibleScope = useRef(viewKey);
  visibleScope.current = viewKey;
  const url = (suffix = '', campusId = scope) => `/admin/delivery-costs${suffix}${suffix.includes('?') ? '&' : '?'}${new URLSearchParams(campusId ? { campus_id: campusId } : {}).toString()}`;
  const load = useCallback(async () => {
    const run = ++generation.current;
    setLoading(true); setError('');
    try {
      const query = scope ? { campus_id: scope } : {};
      const [orders, report, budgets] = await Promise.all([
        apiClient.get('/admin/delivery-costs', { ...query, date: day }),
        apiClient.get('/admin/delivery-costs/report', { ...query, from_date: from, to_date: to }),
        apiClient.get('/admin/delivery-costs/budget', query),
      ]);
      if (run !== generation.current) return;
      setData({ orders: orders.orders, report, budgets, scope, day, from, to });
      setFloor(String(budgets.find(row => row.campus_id === scope)?.floor ?? 0));
    } catch (failure) { if (run === generation.current) { setError(failure.message); setData(null); } }
    finally { if (run === generation.current) setLoading(false); }
  }, [scope, day, from, to]);
  useEffect(() => {
    setData(null); setSelected(new Set()); setEditor(null); setAttempt(null); setHistory(null); setSaveError('');
    load();
    return () => { generation.current += 1; };
  }, [load]);
  const current = data && data.scope === scope && data.day === day && data.from === from && data.to === to ? data : null;
  const groups = useMemo(() => {
    const grouped = new Map<string, any>();
    for (const row of current?.orders || []) {
      const key = `${row.campus_id}:${row.gate_id || 'none'}`;
      if (!grouped.has(key)) grouped.set(key, { key, name: `${row.campus_name} · ${row.gate_name}`, rows: [] });
      grouped.get(key).rows.push(row);
    }
    return [...grouped.values()];
  }, [current]);
  const openEditor = rows => {
    const row = rows[0];
    setEditor({ entry_id: row.entry_id || crypto.randomUUID(), version: row.entry_version || 0,
      campus_id: row.campus_id, kind: row.entry_kind || (rows.length === 1 ? 'order' : 'trip'),
      order_ids: row.entry_id ? row.entry_orders : rows.map(item => item.order_id),
      date: row.entry_date || day, total_cost: row.entry_id ? String(row.entry_total) : '', note: row.entry_note || '', gate: row.gate_name });
    setAttempt(null); setSaveError('');
  };
  const save = async () => {
    if (busy.current || !editor) return;
    const value = Number(editor.total_cost);
    if (!attempt && (editor.total_cost === '' || !Number.isFinite(value) || value < 0 || Math.abs(value * 100 - Math.round(value * 100)) > 0.00001 || !editor.date || editor.date > watDay())) { setSaveError('Enter a valid actual cost, using at most two decimal places, and a date no later than today.'); return; }
    const payload = attempt || { request_id: crypto.randomUUID(), entry_id: editor.entry_id, version: editor.version, kind: editor.kind, date: editor.date, order_ids: editor.order_ids, total_cost: editor.total_cost, note: editor.note };
    const originalScope = viewKey;
    busy.current = true; setSaving(true); setSaveError(''); setAttempt(payload);
    try {
      await apiClient.post(url('', editor.campus_id), payload);
      if (visibleScope.current === originalScope) { setEditor(null); setAttempt(null); setSelected(new Set()); await load(); }
    } catch (failure) {
      if (visibleScope.current !== originalScope) return;
      if (failure.status >= 400 && failure.status < 500) {
        setAttempt(null);
        setSaveError(`${failure.message}${failure.status === 409 ? ' Close this form and refresh to see the latest entry.' : ''}`);
      } else setSaveError('The save result is uncertain. Retry below with the same details; it will not record the cost twice.');
    } finally { busy.current = false; setSaving(false); }
  };
  const showHistory = async row => {
    const originalScope = viewKey;
    try { const entries = await apiClient.get(url(`/history/${row.entry_id}`)); if (visibleScope.current === originalScope) setHistory(entries); }
    catch (failure) { if (visibleScope.current === originalScope) setError(failure.message); }
  };
  const saveFloor = async () => {
    if (busy.current || !scope || !current) return;
    const originalScope = viewKey;
    busy.current = true; setBudgetBusy(true); setError('');
    try {
      await apiClient.patch(url('/budget'), { floor, version: current.budgets.find(row => row.campus_id === scope)?.version ?? 0 });
      if (visibleScope.current === originalScope) await load();
    } catch (failure) { if (visibleScope.current === originalScope) setError(failure.message); }
    finally { busy.current = false; setBudgetBusy(false); }
  };
  const download = async () => {
    if (exporting) return;
    const originalScope = viewKey;
    setExporting(true); setError('');
    try {
      const report = await apiClient.get('/admin/delivery-costs/report', { ...(scope ? { campus_id: scope } : {}), from_date: from, to_date: to, export: '1' });
      if (visibleScope.current !== originalScope) return;
      const columns = ['order_id', 'campus', 'gate', 'delivery_date', 'status', 'payment_status', 'order_total', 'customer_delivery_fee', 'cushion_snapshot', 'recognized_cushion', 'recognized_delivery_fee', 'rider_cost', 'rider_cost_date', 'net_effect'];
      const numeric = new Set(['order_total', 'customer_delivery_fee', 'cushion_snapshot', 'recognized_cushion', 'recognized_delivery_fee', 'rider_cost', 'net_effect']);
      const content = [columns.map(csvCell).join(','), ...report.rows.map(row => columns.map(key => csvCell(row[key] == null ? null : numeric.has(key) ? Number(row[key]) : row[key])).join(','))].join('\r\n');
      const link = document.createElement('a'); const objectUrl = URL.createObjectURL(new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8' }));
      link.href = objectUrl; link.download = `delivery-costs_${from}_${to}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (failure) { if (visibleScope.current === originalScope) setError(failure.message); }
    finally { setExporting(false); }
  };
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-bold flex items-center gap-2"><Truck className="h-5 w-5" />Delivery costs</h2><p className="mt-1 text-sm text-muted-foreground">Record what you paid the rider. See how delivery affects your cushion pool.</p></div><button className={buttonClass} onClick={load} disabled={loading || saving}><RefreshCw className="inline h-4 w-4 mr-1" />Refresh</button></div>
    {error && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
    {loading && !current && <p role="status" className="rounded-xl bg-muted p-4 text-sm">Loading delivery accounting…</p>}
    {current && <>
      {current.budgets.filter(row => Number(row.balance) < Number(row.floor)).map(row => <div key={row.campus_id} role="alert" className="rounded-xl border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950"><AlertTriangle className="inline h-4 w-4 mr-1" /><strong>{row.campus}:</strong> pool {money(row.balance)} is below your {money(row.floor)} floor.{Number(row.balance) < 0 && ' The negative balance is the delivery shortfall covered by Holy Grills.'}</div>)}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">{[
        ['Reconciled pool · all time', current.report.balance], ['Today’s net change', current.report.changes.today], ['This week’s net change', current.report.changes.week], ['This month’s net change', current.report.changes.month],
      ].map(([label, value]) => <div key={label} className="rounded-2xl border border-border bg-card p-4"><p className="text-xs text-muted-foreground">{label}</p><p className={`mt-2 text-lg font-bold break-words ${Number(value) < 0 ? 'text-destructive' : ''}`}>{money(value)}</p></div>)}</div>
      <p className="text-xs text-muted-foreground">Balance = recognized cushion + customer delivery fees − recorded rider costs, for reconciled orders. {current.report.unrecorded_orders} completed/attempted deliveries still need a cost. {money(current.report.unreconciled_collections)} in collections awaits reconciliation. Costs can make the pool negative.</p>
      <section className="rounded-2xl border border-border bg-card p-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-bold">Daily cost entry</h3><label className="text-xs font-semibold">Delivery / cost date <input aria-label="Delivery cost date" type="date" value={day} max={watDay()} onChange={e => setDay(e.target.value)} className={inputClass} /></label></div>
        <p className="text-xs text-muted-foreground">Orders are grouped by campus and gate. Select delivered or failed-delivery orders to split one trip cost evenly. These entries record an expense; they do not send a payment.</p>
        {groups.length === 0 && <p className="py-5 text-center text-sm text-muted-foreground">No paid orders for this date.</p>}
        {groups.map(group => {
          const chosen = group.rows.filter(row => selected.has(row.order_id) && !row.entry_id && row.cost_eligible);
          return <div key={group.key} className="rounded-xl border border-border overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 bg-muted p-3"><h4 className="text-sm font-bold">{group.name}</h4><button className={buttonClass} disabled={!chosen.length || saving} onClick={() => openEditor(chosen)}>Record trip cost ({chosen.length})</button></div>
            {group.rows.map(row => <div key={row.order_id} className="border-t border-border p-3 space-y-2">
              <div className="flex items-start justify-between gap-2"><label className="flex items-start gap-2 text-sm font-bold"><input className="mt-1" aria-label={`Select order ${row.order_id.slice(0, 8)}`} type="checkbox" disabled={!!row.entry_id || !row.cost_eligible || saving} checked={selected.has(row.order_id)} onChange={e => setSelected(previous => { const next = new Set(previous); if (e.target.checked) next.add(row.order_id); else next.delete(row.order_id); return next; })} /><span>#{row.order_id.slice(0, 8).toUpperCase()}<span className="block text-xs font-normal text-muted-foreground capitalize">{row.status.replaceAll('_', ' ')} · {row.payment_status.replaceAll('_', ' ')}</span></span></label><div className="flex flex-wrap gap-2 justify-end"><button className={`${buttonClass} text-xs`} disabled={!row.cost_eligible && !row.entry_id} onClick={() => openEditor([row])}>{row.entry_id ? row.entry_kind === 'trip' ? 'Edit trip cost' : 'Edit cost' : 'Record cost'}</button>{row.entry_id && <button aria-label={`Cost history ${row.order_id.slice(0, 8)}`} onClick={() => showHistory(row)} className="p-2"><History className="h-4 w-4" /></button>}</div></div>
              {row.address && <p className="text-xs text-muted-foreground pl-5">{row.address}</p>}
              <dl className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2 text-xs">{[
                ['Order total', money(row.order_total)], ['Customer delivery fee', money(row.customer_delivery_fee)], ['Cushion at checkout', money(row.cushion_original)], ['Recognized cushion + delivery', money(Number(row.cushion_total) + Number(row.delivery_fee_collected))], ['Actual rider cost', row.rider_cost == null ? 'Not recorded' : money(row.rider_cost)], ['Pool change', row.net_effect == null ? 'Awaiting cost' : money(row.net_effect)],
              ].map(([label, value]) => <div key={label} className="rounded-lg bg-muted/50 p-2"><dt className="text-muted-foreground">{label}</dt><dd className="font-bold mt-1">{value}</dd></div>)}</dl>
            </div>)}
          </div>;
        })}
      </section>
      <section className="rounded-2xl border border-border bg-card p-4"><h3 className="font-bold">Pool by gate · all time</h3><div className="mt-3 overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Campus / gate', 'Cushion', 'Delivery fees', 'Rider costs', 'Pool balance', 'Costs missing'].map(label => <th key={label} className="p-2 whitespace-nowrap">{label}</th>)}</tr></thead><tbody>{current.report.gates.map(row => <tr key={`${row.campus_id}:${row.gate_id}`} className="border-t border-border"><td className="p-2">{row.campus} / {row.gate}</td>{[row.cushion, row.delivery_fees, row.rider_costs, row.balance].map((value, i) => <td key={i} className="p-2 whitespace-nowrap">{money(value)}</td>)}<td className="p-2">{row.unrecorded}</td></tr>)}</tbody></table></div><p className="mt-2 text-xs text-muted-foreground">Cushion and fees include unreconciled collections. Pool balance includes only orders with a recorded cost.</p></section>
    </>}
    <section className="flex flex-wrap items-end gap-3"><label className="text-xs font-semibold">From<input aria-label="Report from" type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} className={`${inputClass} block mt-1`} /></label><label className="text-xs font-semibold">To<input aria-label="Report to" type="date" value={to} min={from} max={watDay()} onChange={e => setTo(e.target.value)} className={`${inputClass} block mt-1`} /></label><button disabled={exporting || !current} onClick={download} className={buttonClass}><Download className="inline w-4 h-4 mr-1" />{exporting ? 'Exporting…' : 'Export orders CSV'}</button></section>
    {current && <BalanceTrend points={current.report.trend || []} />}
    {current && <section className="rounded-2xl border border-border bg-card p-4 space-y-3"><h3 className="font-bold">Pool warning floor</h3><p className="text-xs text-muted-foreground">Warn when the reconciled balance falls below this amount. The pool can still go negative. Default: ₦0.</p>{scope ? <div className="flex flex-wrap items-end gap-2"><label className="text-xs font-semibold">Warning floor (₦)<input aria-label="Pool warning floor" type="number" min="0" step="0.01" value={floor} onChange={e => setFloor(e.target.value)} className={`${inputClass} block mt-1`} /></label><button disabled={budgetBusy || saving || floor === ''} onClick={saveFloor} className={buttonClass}>{budgetBusy ? 'Saving…' : 'Save floor'}</button></div> : <p className="text-sm text-muted-foreground">Select a campus in the header to edit its warning floor. All-campus warnings remain separate for each campus.</p>}</section>}
    {editor && <Modal open title={editor.version ? 'Edit delivery cost' : 'Record delivery cost'} onClose={() => { if (!saving && !attempt) setEditor(null); }}>
      <div className="space-y-4"><p className="text-sm">{editor.gate} · {editor.order_ids.length} order{editor.order_ids.length === 1 ? '' : 's'}. {editor.kind === 'trip' ? 'The total is split evenly, with any remaining kobo allocated once.' : 'Enter the actual amount paid.'}</p>
        <Field label="Actual rider cost (₦)"><TextInput aria-label="Actual rider cost" type="number" min="0" step="0.01" disabled={saving || !!attempt} value={editor.total_cost} onChange={e => setEditor({ ...editor, total_cost: e.target.value })} /></Field>
        <Field label="Date paid"><TextInput aria-label="Date paid" type="date" max={watDay()} disabled={saving || !!attempt} value={editor.date} onChange={e => setEditor({ ...editor, date: e.target.value })} /></Field>
        <Field label="Note (optional)"><TextInput aria-label="Cost note" maxLength={500} disabled={saving || !!attempt} value={editor.note} onChange={e => setEditor({ ...editor, note: e.target.value })} /></Field>
        <p className="text-xs text-muted-foreground">The customer’s charge stays unchanged. Any shortfall reduces the pool; a surplus increases it. Previous versions remain in history.</p>
        {saveError && <p role="alert" className="text-sm text-destructive">{saveError}</p>}
        <button disabled={saving} className="w-full rounded-full bg-primary text-primary-foreground py-3 font-bold disabled:opacity-50" onClick={save}>{saving ? 'Saving…' : attempt ? 'Retry same save' : 'Save actual cost'}</button>
      </div>
    </Modal>}
    {history && <Modal open title="Delivery cost history" onClose={() => setHistory(null)}><div className="space-y-3">{history.map(record => <div key={record.id} className="rounded-xl border border-border p-3 text-sm"><p className="font-bold">Version {record.after_values.entry.version} · {money(record.after_values.entry.total_cost)}</p><p className="text-xs text-muted-foreground">{new Date(record.occurred_at).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })} WAT · {record.after_values.entry.cost_date}</p><p>{record.after_values.entry.note}</p><p className="text-xs">{record.after_values.allocations.length} orders · recorded by {record.actor_id}</p></div>)}</div></Modal>}
  </div>;
}
