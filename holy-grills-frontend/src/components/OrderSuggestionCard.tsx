import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flame, X, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const DISMISS_KEY = 'hg_suggestion_dismissed';

/**
 * OrderSuggestionCard — "You ordered X last time — reorder?"
 * Sourced from GET /orders/suggestions. Dismissible per session only:
 * it reappears on the next visit, never a permanent opt-out.
 */
export default function OrderSuggestionCard() {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [suggestion, setSuggestion] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
  });

  useEffect(() => {
    if (!isAuthenticated || dismissed) return;
    liveApi.orders.getSuggestion()
      .then((res) => {
        const s = res?.suggestion ?? null;
        if (s && s.order_id && Array.isArray(s.items) && s.items.length) setSuggestion(s);
      })
      .catch(() => {});
  }, [isAuthenticated, dismissed]);

  if (!isAuthenticated || dismissed || !suggestion) return null;

  const dismiss = () => {
    try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
    setDismissed(true);
  };

  const handleReorder = async () => {
    setBusy(true);
    try {
      await liveApi.orders.reorder(suggestion.order_id);
      toast({ title: msg('FE_ORDER_SUGGESTION_CARD_LAST_ORDER_ADDED_TO_YOUR_CART', '🔥 Last order added to your cart'), description: msg('FE_ORDER_SUGGESTION_CARD_PICK_UP_WHERE_YOU_LEFT_OFF', 'Pick up where you left off.') });
      navigate('/cart');
    } catch (e) {
      toast({ title: msg('FE_ORDER_SUGGESTION_CARD_COULD_NOT_REORDER', 'Could not reorder'), description: e.message || 'Please try again.', variant: 'destructive' });
    }
    setBusy(false);
  };

  const names = suggestion.items.slice(0, 3).map((i) => `${i.quantity}× ${i.name}`).join(', ');
  const extra = suggestion.items.length > 3 ? ` +${suggestion.items.length - 3} more` : '';

  return (
    <div className="rounded-2xl bg-card border border-border p-3.5 flex items-center gap-3 shadow-card animate-fade-in">
      <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
        <Flame className="w-5 h-5 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-bold text-foreground">You ordered {names}{extra} last time</div>
        <button onClick={handleReorder} disabled={busy} className="text-xs font-bold text-primary hover:underline disabled:opacity-60 mt-0.5">
          {busy ? <span className="inline-flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Adding…</span> : 'Reorder in one tap →'}
        </button>
      </div>
      <button onClick={dismiss} className="text-muted-foreground hover:text-foreground transition-colors shrink-0 p-1" aria-label="Dismiss suggestion">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}