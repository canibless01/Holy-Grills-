import { useState, useEffect, useMemo } from 'react';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { formatDateTime } from '@/lib/hgUtils';
import HpHistorySkeleton from '@/components/skeletons/HpHistorySkeleton';
import MascotStandee from '@/components/mascot/MascotStandee';

const TYPE_LABELS = {
  earn: 'Earned',
  spend: 'Spent',
  unlock: 'Unlocked',
  expire: 'Expired',
  reward: 'Reward',
  refund: 'Refund',
  transfer: 'Transfer',
  grant: 'Granted',
  decay: 'Decayed',
};

/**
 * HpHistoryLedger — the confirmed HP history ledger. Every HP transaction
 * (earn/spend/unlock/expire) listed with amount, type, source, reference ID and
 * timestamp. Scrollable + filterable by type. Immutable list from
 * GET /hp/transactions. Positive amounts are green (earned), negative are red
 * (spent/decayed).
 */
export default function HpHistoryLedger() {
  const [txns, setTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await mockApi.hp.getTransactions({ limit: 200 });
        const list = res?.transactions || res?.items || (Array.isArray(res) ? res : []);
        if (!cancelled) setTxns(list);
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const types = useMemo(() => {
    const set = new Set(txns.map((t) => t.type).filter(Boolean));
    return ['all', ...Array.from(set)];
  }, [txns]);

  const filtered = filter === 'all' ? txns : txns.filter((t) => t.type === filter);

  if (loading) return <HpHistorySkeleton />;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading font-bold text-lg text-foreground">HP History</h2>
        <span className="hg-caption">{txns.length} transactions</span>
      </div>

      {/* Filter pills */}
      <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1 pb-1">
        {types.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-pill text-xs font-bold transition-all ${filter === t ? 'bg-gradient-cta text-white' : 'bg-card text-muted-foreground border border-border'}`}
          >
            {t === 'all' ? 'All' : TYPE_LABELS[t] || t}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-10">
          <MascotStandee mascot="waving" className="w-24 h-24 mx-auto mb-1" alt="No HP transactions yet" />
          <p className="text-sm text-muted-foreground">No HP transactions yet</p>
          <p className="text-xs text-muted-foreground mt-1">Order food to start earning Holy Points.</p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-[420px] overflow-y-auto scrollbar-hide -mx-1 px-1">
          {filtered.map((t) => {
            const positive = (t.amount || 0) > 0;
            const isSpend = t.type === 'spend' || t.type === 'transfer' || t.type === 'decay';
            const credit = positive && !isSpend;
            return (
              <div key={t.id} className="flex items-center gap-3 p-3 rounded-xl bg-card border border-border">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${credit ? 'bg-green-50' : 'bg-red-50'}`}>
                  {credit ? <ArrowDownLeft className="w-4 h-4 text-green-600" /> : <ArrowUpRight className="w-4 h-4 text-red-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-foreground truncate">
                    {t.description || t.source || TYPE_LABELS[t.type] || 'Transaction'}
                  </div>
                  <div className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                    <span className="capitalize">{TYPE_LABELS[t.type] || t.type || '—'}</span>
                    {t.reference_id && <span>· #{String(t.reference_id).slice(0, 8)}</span>}
                    <span>· {formatDateTime(t.created_date || t.created_at)}</span>
                  </div>
                </div>
                <div className={`font-bold text-sm whitespace-nowrap ${credit ? 'text-green-600' : 'text-red-500'}`}>
                  {credit ? '+' : ''}{t.amount || 0} HP
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}