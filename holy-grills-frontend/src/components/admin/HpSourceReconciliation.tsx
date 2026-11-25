import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';

export default function HpSourceReconciliation({ range }: { range: Record<string, string> }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const from = range.from_date; const to = range.to_date;
  useEffect(() => {
    let active = true; setData(null); setError('');
    liveApi.analytics.hpReconciliation({ from_date: from, to_date: to }).then(result => { if (active) setData(result); }).catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [from, to, retry]);
  return <section className="rounded-2xl border border-border bg-card p-4 space-y-3">
    <h2 className="font-bold">{msg('FE_HP_SOURCE_REPORT', 'HP balances by source')}</h2>
    <p className="text-xs text-muted-foreground">{msg('FE_HP_REPORT_BASIS', 'Active and pending balances are current. Awards and spending use the selected period. Pending awards are not spendable; source balances use the unspent ledger amounts.')}</p>
    {error ? <p role="alert" className="text-destructive">{error} <button type="button" className="underline" onClick={() => setRetry(n => n + 1)}>{msg('FE_LOOKUP_RETRY', 'Retry')}</button></p> : !data ? <p role="status">{msg('FE_HP_REPORT_LOADING', 'Loading HP reconciliation…')}</p> : <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div><span>{msg('FE_HP_ACTIVE_BALANCE', 'Account active HP')}</span><strong className="block">{Number(data.profile_active_balance).toLocaleString()}</strong></div>
        <div><span>{msg('FE_HP_LEDGER_BALANCE', 'Unspent ledger HP')}</span><strong className="block">{Number(data.ledger_active_remaining).toLocaleString()}</strong></div>
        <div><span>{msg('FE_HP_PENDING_BALANCE', 'Pending HP')}</span><strong className="block">{Number(data.pending_amount).toLocaleString()}</strong></div>
        <div><span>{msg('FE_HP_BALANCE_DIFFERENCE', 'Reconciliation difference')}</span><strong className="block">{Number(data.active_balance_difference).toLocaleString()}</strong></div>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th>{msg('FE_HP_SOURCE', 'Source')}</th><th>{msg('FE_HP_LEDGER_BALANCE', 'Unspent ledger HP')}</th><th>{msg('FE_HP_PENDING_BALANCE', 'Pending HP')}</th><th>{msg('FE_HP_PERIOD_AWARDED', 'Active awards in period')}</th></tr></thead><tbody>{(data.sources || []).map(row => <tr className="border-t" key={row.source}><td className="py-2">{row.source}</td><td>{Number(row.active_remaining).toLocaleString()}</td><td>{Number(row.pending).toLocaleString()}</td><td>{Number(row.active_awarded_in_period).toLocaleString()}</td></tr>)}</tbody></table></div>
    </>}
  </section>;
}
