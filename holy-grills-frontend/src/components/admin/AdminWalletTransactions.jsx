import React, { useState, useEffect, useCallback } from 'react';
import { Wallet, RefreshCw, ArrowDownLeft, ArrowUpRight, Clock } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, formatDateTime, timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Pill, Pagination, Segmented, SectionTitle } from './ui/AdminKit';

// Wallet Transactions — GET /wallet/admin/transactions.
// The admin-side view of every wallet movement across all users: funding,
// spending, refunds and adjustments. Filter by direction and page through the
// full ledger; each row expands to show the reference and the exact timestamp.
const PAGE_SIZE = 25;

const FILTERS = [
  { id: '', label: 'All' },
  { id: 'credit', label: 'Credit' },
  { id: 'debit', label: 'Debit' },
];

// Field picker — the backend has used more than one name for these over time,
// so read the first present, non-object value rather than assuming one shape.
const pick = (t, keys, fallback = '') => {
  for (const k of keys) {
    const v = t && t[k];
    if (v != null && v !== '' && typeof v !== 'object') return v;
  }
  return fallback;
};

const text = (v, fallback = '') => {
  if (v == null) return fallback;
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (typeof v === 'object') return v.full_name || v.name || v.email || v.code || fallback;
  return fallback;
};

const DEBIT_WORDS = ['debit', 'withdraw', 'spend', 'spent', 'charge', 'deduction', 'payment'];

const isDebit = (t) => {
  const raw = String(pick(t, ['direction', 'type', 'transaction_type', 'kind', 'category'], '')).toLowerCase();
  return DEBIT_WORDS.some((w) => raw.includes(w));
};

export default function AdminWalletTransactions() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [open, setOpen] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await liveApi.wallet.getWalletTransactions({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        ...(filter ? { type: filter } : {}),
      });
      const list = Array.isArray(res) ? res : [];
      setRows(list);
      setHasMore(list.length === PAGE_SIZE);
    } catch (e) {
      toast({ title: "Couldn't load wallet transactions", description: e.message, variant: 'destructive' });
      setRows([]);
      setHasMore(false);
    }
    setLoading(false);
  }, [page, filter]);

  useEffect(() => { load(); }, [load]);

  const onFilter = (id) => { setFilter(id); setPage(0); };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <SectionTitle
          icon={Wallet}
          title="Wallet transactions"
          sub="Every funding, spend and refund across all users"
          right={
            <div className="flex items-center gap-2 shrink-0">
              <Segmented options={FILTERS} value={filter} onChange={onFilter} />
              <button
                onClick={load}
                disabled={loading}
                aria-label="Refresh"
                className="w-9 h-9 rounded-full bg-secondary border border-border flex items-center justify-center text-muted-foreground hover:text-primary disabled:opacity-50 active:scale-95 transition"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          }
        />
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} transaction{rows.length === 1 ? '' : 's'} on this page
        </p>
      </Card>

      {loading && rows.length === 0 ? (
        <div className="space-y-2.5">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={Wallet}
            title="No wallet transactions found"
            body={filter ? 'No transactions match this filter. Try "All".' : 'Wallet funding and spending appear here as they happen.'}
          />
        </Card>
      ) : (
        <>
          <div className="space-y-2.5">
            {rows.map((t, i) => {
              const debit = isDebit(t);
              const amount = Number(pick(t, ['amount', 'value', 'amount_naira'], 0)) || 0;
              const who =
                text(t && t.user) ||
                text(pick(t, ['user_name', 'full_name', 'email'], '')) ||
                text(pick(t, ['user_id', 'wallet_id'], '')) ||
                'Unknown user';
              const label = pick(t, ['description', 'narrative', 'reason', 'note'], '') ||
                pick(t, ['type', 'transaction_type', 'kind'], 'Transaction');
              const status = pick(t, ['status', 'state'], '');
              const reference = pick(t, ['reference', 'reference_code', 'reference_id', 'tx_ref', 'payment_reference'], '');
              const when = pick(t, ['created_at', 'date', 'timestamp', 'updated_date'], '');
              const id = pick(t, ['id', 'transaction_id'], `row-${i}`);
              const expanded = open === id;

              return (
                <Card key={id} className="p-0 overflow-hidden">
                  <button
                    onClick={() => setOpen(expanded ? null : id)}
                    className="w-full flex items-center gap-3 p-3.5 text-left hover:bg-secondary/40 transition-colors"
                  >
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${debit ? 'bg-destructive/10' : 'bg-success/15'}`}>
                      {debit
                        ? <ArrowUpRight className="w-5 h-5 text-destructive" />
                        : <ArrowDownLeft className="w-5 h-5 text-success" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-sm text-foreground truncate capitalize">{text(label).replace(/_/g, ' ')}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{who}</div>
                      {when && (
                        <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5">
                          <Clock className="w-3 h-3" /> {timeAgo(when)}
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className={`font-heading font-extrabold text-sm tabular-nums ${debit ? 'text-destructive' : 'text-success'}`}>
                        {debit ? '−' : '+'}{formatNaira(amount)}
                      </div>
                      {status && (
                        <Pill tone={String(status).toLowerCase() === 'success' || String(status).toLowerCase() === 'completed' ? 'green' : String(status).toLowerCase() === 'pending' ? 'amber' : 'outline'}>
                          {text(status)}
                        </Pill>
                      )}
                    </div>
                  </button>

                  {expanded && (
                    <div className="px-3.5 pb-3.5 pt-0 space-y-1.5 border-t border-border">
                      <Detail label="Direction" value={debit ? 'Debit' : 'Credit'} />
                      <Detail label="Amount" value={formatNaira(amount)} />
                      <Detail label="User" value={who} />
                      <Detail label="Reference" value={reference || '—'} />
                      <Detail label="Status" value={text(status, '—')} />
                      <Detail label="Date" value={when ? formatDateTime(when) : '—'} />
                    </div>
                  )}
                </Card>
              );
            })}
          </div>

          {(page > 0 || hasMore) && (
            <Card className="p-3">
              <Pagination
                page={page}
                canPrev={page > 0}
                canNext={hasMore}
                onPrev={() => setPage((p) => Math.max(0, p - 1))}
                onNext={() => setPage((p) => p + 1)}
                busy={loading}
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function Detail({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[11px]">
      <span className="font-bold text-muted-foreground uppercase tracking-wide shrink-0">{label}</span>
      <span className="text-foreground font-semibold text-right break-all">{value}</span>
    </div>
  );
}