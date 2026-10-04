import React, { useState, useEffect } from 'react';
import { X, Gift, Loader2, Check } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';

// POST /free-sides/redeem { side_choice, order_id } — attaches a free side to an
// existing order in a modifiable status. The available side choices come from
// GET /free-sides (available_sides); credits are earned via leaderboard top-10.
export default function FreeSideRedemptionModal({ orderId, onClose, onSuccess }) {
  const [loading, setLoading] = useState(true);
  const [credits, setCredits] = useState({ count: 0, available_sides: [], expires_at: null });
  const [choice, setChoice] = useState('');
  const [redeeming, setRedeeming] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await liveApi.rewards.getFreeSideCredits();
        const sides = Array.isArray(res?.available_sides) ? res.available_sides : [];
        setCredits({ count: res?.count ?? 0, available_sides: sides, expires_at: res?.expires_at ?? null });
        if (sides.length === 1) setChoice(sides[0]);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  const handleRedeem = async () => {
    if (!choice) return;
    setRedeeming(true);
    try {
      await liveApi.rewards.redeemFreeSide({ side_choice: choice, order_id: orderId });
      toast({ title: '🎁 Free side added!', description: `${choice} will be added to your order.` });
      onSuccess?.();
      onClose();
    } catch (e) {
      toast({ title: 'Could not add free side', description: e.message, variant: 'destructive' });
    }
    setRedeeming(false);
  };

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={onClose}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-sm animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Gift className="w-5 h-5 text-primary" /> Add Free Side</h3>
            <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
          </div>

          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
          ) : credits.count === 0 ? (
            <div className="text-center py-8">
              <Gift className="w-10 h-10 text-accent mx-auto mb-2" />
              <p className="text-sm font-semibold text-foreground">No free side credits</p>
              <p className="text-xs text-muted-foreground mt-1">Earn a top-10 leaderboard finish to unlock a free side.</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                You have <span className="font-bold text-foreground">{credits.count}</span> free side credit{credits.count !== 1 ? 's' : ''}. Pick one to add to this order.
              </p>
              <div className="space-y-2">
                {(credits.available_sides || []).map((s) => (
                  <button key={s} onClick={() => setChoice(s)} className={`w-full flex items-center justify-between p-3 rounded-2xl border-2 transition-all ${choice === s ? 'border-primary/40 bg-primary/5' : 'border-border hover:border-input'}`}>
                    <span className="font-medium text-sm text-foreground">{s}</span>
                    {choice === s && <Check className="w-4 h-4 text-primary" />}
                  </button>
                ))}
              </div>
              <button onClick={handleRedeem} disabled={redeeming || !choice} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 transition-all active:scale-[0.98]">
                {redeeming ? <><Loader2 className="w-4 h-4 animate-spin" /> Adding…</> : 'Add Free Side'}
              </button>
            </div>
          )}
        </div>
      </div>
    </ModalPortal>
  );
}