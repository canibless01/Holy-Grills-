import { useState } from 'react';
import { X, Send, Loader2, Flag } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';

// Reads the real response shape from GET /marketplace/purchases:
// each row carries nested marketplace_listings(title, listing_type, image_url)
// and metadata.code (set when the purchase is fulfilled). The old code read
// p.listing_title / p.code which the route never returns.
const purchaseTitle = (p) => p?.marketplace_listings?.title || p?.title || 'Listing';
const purchaseCode = (p) => p?.metadata?.code || p?.code;

const STATUS_TONE = {
  pending: 'amber', completed: 'green', refunded: 'blue', cancelled: 'red',
};

export default function MarketplacePurchasesPanel({ purchases, loading, onRefresh }) {
  const [reporting, setReporting] = useState(null); // purchase row being reported
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submitReport = async () => {
    setSubmitting(true);
    try {
      const res = await liveApi.marketplace.reportPurchaseProblem(reporting.id, { reason: reason.trim() });
      toast({ title: 'Report sent', description: res?.message || 'Your report was sent to the admins.' });
      setReporting(null);
      setReason('');
      onRefresh?.();
    } catch (e) {
      toast({ title: 'Could not send report', description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <div className="rounded-3xl bg-card border border-border p-4 shadow-card space-y-2">
      <h3 className="font-bold text-sm text-foreground mb-2">My Purchases</h3>
      {loading ? (
        <p className="text-xs text-muted-foreground text-center py-3">Loading…</p>
      ) : purchases.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-3">Nothing here yet.</p>
      ) : (
        purchases.map((p) => {
          const code = purchaseCode(p);
          const tone = STATUS_TONE[p.status] || 'cocoa';
          return (
            <div key={p.id} className="flex items-center justify-between gap-2 p-3 rounded-xl bg-muted">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground truncate">{purchaseTitle(p)}</div>
                <div className="text-[10px] text-muted-foreground">{timeAgo(p.created_at)} · <span className={`font-bold ${p.status === 'completed' ? 'text-success' : p.status === 'refunded' ? 'text-blue-600' : p.status === 'cancelled' ? 'text-destructive' : ''}`}>{p.status}</span></div>
                {code && <div className="font-mono font-bold text-sm text-primary mt-0.5">{code}</div>}
              </div>
              {p.status === 'completed' && (
                <button onClick={() => setReporting(p)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-full bg-card border border-border text-[10px] font-bold text-foreground shrink-0">
                  <Flag className="w-3 h-3" /> Report
                </button>
              )}
            </div>
          );
        })
      )}

      {reporting && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !submitting && setReporting(null)}>
          <div className="bg-card rounded-t-3xl sm:rounded-3xl p-5 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-heading font-bold text-base text-foreground">Report a Problem</h3>
              <button onClick={() => setReporting(null)} className="p-1 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <p className="text-xs text-muted-foreground mb-2">Tell us what's wrong with <span className="font-semibold text-foreground">{purchaseTitle(reporting)}</span>. An admin will review and replace or refund it.</p>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              maxLength={500}
              placeholder="e.g., The code says invalid when I try to redeem it…"
              className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40 bg-card resize-none"
            />
            <p className="text-[10px] text-muted-foreground mt-1 text-right">{reason.length}/500</p>
            <button
              onClick={submitReport}
              disabled={submitting || reason.trim().length < 5}
              className="w-full mt-2 py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Sending…</> : <><Send className="w-4 h-4" /> Send Report</>}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}