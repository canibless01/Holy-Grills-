import { useState } from 'react';
import { X, Gift } from 'lucide-react';
import { motion } from 'framer-motion';
import ModalPortal from '@/components/ModalPortal';
import type { FreeSideItem } from '@/types/free-sides';

/**
 * Checkout pop-up that appears when the user has free side credits. The options
 * are the backend's curated free-side items (GET /free-sides → available_sides),
 * so the chosen item is the one the credit is actually spent on: Checkout calls
 * POST /free-sides/select and the backend consumes the selection when the order
 * is placed (docs/WIRING_AUDIT.md §3.1).
 */
export default function FreeSideCreditModal({ open, count, sides = [], busy = false, onClose, onUse }: {
  open: boolean;
  count: number;
  /** The backend's curated items (GET /free-sides → available_sides). */
  sides?: FreeSideItem[];
  busy?: boolean;
  onClose: () => void;
  onUse: (item: FreeSideItem) => void;
}) {
  const [choiceId, setChoiceId] = useState<string | null>(null);
  // First render has no stored id; fall back to the first curated item.
  const choice = sides.find((s) => s.id === choiceId) || sides[0] || null;

  if (!open || count <= 0) return null;

  const handleUse = () => {
    if (!choice || busy) return;
    onUse(choice);
  };

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={onClose}>
      <motion.div
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="bg-card rounded-3xl p-6 w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center">
              <Gift className="w-4 h-4 text-white" />
            </div>
            <h3 className="font-heading font-bold text-lg text-foreground">Free side credit!</h3>
          </div>
          <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>

        <p className="text-sm text-foreground mb-1">
          You have <span className="font-bold text-primary">{count}</span> free side credit{count !== 1 ? 's' : ''}!
        </p>
        <p className="text-xs text-muted-foreground mb-4">Pick a side — it's added to this order at ₦0. The credit is used the moment you place the order.</p>

        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Choose your free side</label>
        {sides.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            No free sides are available on the menu right now — your credit stays on your account.
          </p>
        ) : (
          <select
            value={choice?.id ?? ''}
            onChange={(e) => setChoiceId(e.target.value)}
            className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm font-semibold text-foreground bg-card focus:outline-none focus:border-primary/40"
          >
            {sides.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        )}

        <div className="mt-4 space-y-2">
          <button
            onClick={handleUse}
            disabled={!choice || busy}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-[0.98] transition-transform disabled:opacity-50"
          >
            {busy ? 'Adding…' : 'Add free side · ₦0 🏆'}
          </button>
          <button onClick={onClose} className="w-full py-2.5 rounded-full text-muted-foreground font-semibold text-xs">
            Skip for now
          </button>
        </div>
      </motion.div>
    </div>
    </ModalPortal>
  );
}