import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import FlameMark from '@/components/FlameMark';
import MascotStandee from '@/components/mascot/MascotStandee';
import { formatNaira, timeAgo, HP_SOURCE_LABELS } from '@/lib/hgUtils';

const WALLET_TX_TYPES = {
  topup: { label: 'Wallet Top-up', isCredit: true },
  order_payment: { label: 'Order Payment', isCredit: false },
  refund: { label: 'Refund', isCredit: true },
  withdrawal: { label: 'Withdrawal', isCredit: false },
  bank_transfer: { label: 'Bank Transfer', isCredit: true },
};

const HP_DEBIT_SOURCES = ['redemption', 'redeem', 'transfer_out', 'transfer', 'spend', 'expire', 'expired', 'marketplace_purchase'];

const normalizeWalletTx = (tx) => {
  const info = WALLET_TX_TYPES[tx.type] || { label: tx.reason || tx.type || 'Transaction', isCredit: tx.amount > 0 };
  return {
    id: tx.id,
    kind: 'cash',
    label: tx.reason || info.label,
    sublabel: info.label,
    amount: Math.abs(Number(tx.amount) || 0),
    isCredit: info.isCredit,
    date: tx.created_at,
    balanceAfter: tx.balance_after,
  };
};

const normalizeHpTx = (tx) => {
  const rawAmount = Number(tx.amount ?? tx.hp_amount ?? tx.points ?? 0);
  const source = tx.source || tx.type || tx.reason || '';
  const isDebit = rawAmount < 0 || HP_DEBIT_SOURCES.some((s) => source.toLowerCase().includes(s));
  return {
    id: tx.id,
    kind: 'hp',
    label: HP_SOURCE_LABELS[source] || source || 'HP Transaction',
    sublabel: 'Holy Points',
    amount: Math.abs(rawAmount),
    isCredit: !isDebit,
    date: tx.created_at,
    balanceAfter: null,
  };
};

const TABS = [
  { key: 'all', label: 'All' },
  { key: 'cash', label: 'Cash' },
  { key: 'hp', label: 'HP' },
];

export default function WalletTransactionList({ walletTxns, hpTxns, activeTab, onTabChange, loading }) {
  const normalized = [
    ...walletTxns.map(normalizeWalletTx),
    ...hpTxns.map(normalizeHpTx),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  const filtered = activeTab === 'all' ? normalized : normalized.filter((t) => t.kind === activeTab);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-heading font-bold text-sm text-foreground">Transaction History</h3>
        <div className="flex gap-1 p-1 rounded-full bg-secondary">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
                activeTab === t.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border">
              <div className="w-10 h-10 rounded-full bg-muted animate-pulse" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3 w-24 rounded bg-muted animate-pulse" />
                <div className="h-2.5 w-16 rounded bg-muted animate-pulse" />
              </div>
              <div className="h-4 w-16 rounded bg-muted animate-pulse" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-10">
          <MascotStandee mascot="thinking" className="w-24 h-24 mx-auto mb-2" alt="No transactions yet" />
          <p className="text-sm text-muted-foreground">No transactions yet</p>
          <p className="text-xs text-muted-foreground/60 mt-1">Fund your wallet or earn HP to see activity here</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((tx) => (
            <div key={`${tx.kind}-${tx.id}`} className="flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border transition-all hover:shadow-card">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                tx.kind === 'hp' ? (tx.isCredit ? 'bg-amber-100' : 'bg-orange-100') : (tx.isCredit ? 'bg-success/10' : 'bg-destructive/10')
              }`}>
                {tx.kind === 'hp'
                  ? <FlameMark className="w-5 h-5" />
                  : tx.isCredit ? <ArrowDownLeft className="w-5 h-5 text-success" /> : <ArrowUpRight className="w-5 h-5 text-destructive" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm text-foreground truncate">{tx.label}</div>
                <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <span>{timeAgo(tx.date)}</span>
                  {tx.kind === 'hp' && <span className="px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600 text-[9px] font-bold">HP</span>}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className={`font-bold text-sm tabular-nums ${tx.isCredit ? 'text-success' : 'text-destructive'}`}>
                  {tx.isCredit ? '+' : '-'}{tx.kind === 'hp' ? `${tx.amount} HP` : formatNaira(tx.amount)}
                </div>
                {tx.balanceAfter != null && (
                  <div className="text-[10px] text-muted-foreground tabular-nums">Bal {formatNaira(tx.balanceAfter)}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}