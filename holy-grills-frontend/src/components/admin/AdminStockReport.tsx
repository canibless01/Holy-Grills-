import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '@/lib/apiClient';
import { csvCell } from '@/lib/csvCell';
import { msg } from '@/lib/messages';

const watDay = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lagos', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const amount = new Intl.NumberFormat('en-NG', { maximumFractionDigits: 6 });
const currency = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', minimumFractionDigits: 2 });
const control = 'rounded-xl border border-border bg-card px-3 py-2 text-sm';

export default function AdminStockReport({ campusId }) {
  const [from, setFrom] = useState(() => `${watDay().slice(0, 8)}01`);
  const [to, setTo] = useState(watDay);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const scope = campusId || '';
  const load = useCallback(async () => {
    const run = ++generation.current;
    setLoading(true); setError('');
    try {
      const value = await apiClient.get('/admin/stock-items/report', { ...(scope ? { campus_id: scope } : {}), from_date: from, to_date: to });
      if (run === generation.current) setResult({ ...value, scope, from, to });
    } catch (failure) { if (run === generation.current) { setError(failure.message); setResult(null); } }
    finally { if (run === generation.current) setLoading(false); }
  }, [scope, from, to]);
  useEffect(() => { setResult(null); load(); return () => { generation.current += 1; }; }, [load]);
  const current = result?.scope === scope && result?.from === from && result?.to === to ? result : null;
  const rows = current?.items || [];
  const mismatch = rows.filter(row => Number(row.drift) !== 0 || Number(row.scope_mismatches) !== 0).length;
  const exportCsv = () => {
    if (!current) return;
    const fields = ['campus', 'name', 'unit', 'archived', 'opening', 'purchased', 'used', 'wasted', 'corrected', 'closing', 'current_balance', 'ledger_balance', 'drift', 'purchase_cost', 'uncosted_purchases', 'scope_mismatches'];
    const cell = value => `"${typeof value === 'number' ? String(value) : csvCell(value)}"`;
    const content = [fields.map(cell).join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `stock_${from}_${to}.csv`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-4" aria-label="Stock reconciliation report">
    <div><h3 className="font-bold">{msg('FE_STOCK_REPORT_TITLE', 'Stock reconciliation & report')}</h3><p className="mt-1 text-xs text-muted-foreground">{msg('FE_STOCK_REPORT_HELP', 'Opening + purchases − usage − waste + corrections = period closing. Current balance is checked against the full ledger. Quantities use each ingredient’s usage unit.')}</p></div>
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs font-semibold">{msg('FE_STOCK_REPORT_FROM', 'From')}<input aria-label="Stock report from" type="date" value={from} max={to} onChange={event => setFrom(event.target.value)} className={`${control} block mt-1`} /></label>
      <label className="text-xs font-semibold">{msg('FE_STOCK_REPORT_TO', 'To')}<input aria-label="Stock report to" type="date" value={to} min={from} max={watDay()} onChange={event => setTo(event.target.value)} className={`${control} block mt-1`} /></label>
      <button disabled={loading} onClick={load} className={`${control} font-bold disabled:opacity-50`}>{msg('FE_STOCK_REPORT_REFRESH', 'Refresh report')}</button>
      <button disabled={!current || loading} onClick={exportCsv} className={`${control} font-bold disabled:opacity-50`}>{msg('FE_STOCK_REPORT_EXPORT', 'Export stock CSV')}</button>
    </div>
    {loading && <p role="status" className="text-sm text-muted-foreground">{msg('FE_STOCK_REPORT_LOADING', 'Loading stock report…')}</p>}
    {error && <div role="alert" className="text-sm text-destructive">{error}<button onClick={load} className="ml-3 font-bold underline">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>}
    {current && <>
      <div className="flex flex-wrap gap-4 text-sm"><span>{rows.length} {msg('FE_STOCK_REPORT_INGREDIENTS', 'ingredients')}</span><span className={mismatch ? 'font-bold text-destructive' : 'text-success'}>{mismatch} {msg('FE_STOCK_REPORT_MISMATCHES', 'reconciliation issues')}</span><span>{msg('FE_STOCK_REPORT_COST', 'Recorded purchase cost')}: {currency.format(rows.reduce((total, row) => total + Number(row.purchase_cost), 0))}</span></div>
      {rows.some(row => Number(row.uncosted_purchases) > 0) && <p className="text-xs text-muted-foreground">{msg('FE_STOCK_REPORT_UNKNOWN_COSTS', 'Some purchases have no cost recorded. The cost total includes known amounts only.')}</p>}
      {!rows.length ? <p className="py-3 text-sm text-muted-foreground">{msg('FE_STOCK_REPORT_EMPTY', 'No ingredients in this campus scope.')}</p> : <div className="overflow-x-auto"><table className="w-full text-xs text-left"><thead><tr>{['Ingredient / campus', 'Usage unit', 'Opening', 'Purchased', 'Used', 'Wasted', 'Corrections', 'Period closing', 'Current', 'Ledger', 'Difference', 'Purchase cost'].map(label => <th key={label} className="p-2 whitespace-nowrap">{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t border-border"><td className="p-2 min-w-40"><strong>{row.name}</strong><span className="block text-muted-foreground">{row.campus}{row.archived ? ' · Archived' : ''}</span>{Number(row.scope_mismatches) > 0 && <span className="block text-destructive">Ledger campus mismatch</span>}</td><td className="p-2">{row.unit}</td>{['opening', 'purchased', 'used', 'wasted', 'corrected', 'closing', 'current_balance', 'ledger_balance', 'drift'].map(field => <td key={field} className={`p-2 whitespace-nowrap ${field === 'drift' && Number(row.drift) !== 0 ? 'font-bold text-destructive' : ''}`}>{amount.format(Number(row[field]))}</td>)}<td className="p-2 whitespace-nowrap">{currency.format(Number(row.purchase_cost))}{Number(row.uncosted_purchases) > 0 && <span className="block text-muted-foreground">{row.uncosted_purchases} without cost</span>}</td></tr>)}</tbody></table></div>}
      <p className="text-xs text-muted-foreground">{msg('FE_STOCK_REPORT_READ_ONLY', 'Archived ingredients remain in this report. Reconciliation is read-only; it never changes a balance or creates a correction.')}</p>
    </>}
  </section>;
}
