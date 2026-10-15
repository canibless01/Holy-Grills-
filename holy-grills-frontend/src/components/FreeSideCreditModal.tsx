import { msg, useMessages } from '@/lib/messages';
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
  useMessages();
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
    <div className="fixed inset-0 z-50 hg-scrim flex items-center justify-center p-4" onClick={onClose}>
      <motion.div
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        role="dialog" aria-modal="true" aria-labelledby="free-side-title" className="bg-card rounded-3xl p-6 w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center">
              <Gift className="w-4 h-4 text-white" />
            </div>
            <h3 id="free-side-title" className="font-heading font-bold text-lg text-foreground">{msg('FE_FREE_SIDE_MODAL_TITLE', 'Free side credit!')}</h3>
          </div>
          <button onClick={onClose} aria-label={msg('FE_FREE_SIDE_CLOSE', 'Close free-side selection')}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>

        <p className="text-sm text-foreground mb-1">
          {msg('FE_FREE_SIDE_CREDIT_COUNT', 'Free-side credits: {count}', { count })}
        </p>
        <p className="text-xs text-muted-foreground mb-4">{msg('FE_FREE_SIDE_MODAL_HELP', 'Pick a side to add at ₦0. Its credit is used only when the order is saved successfully.')}</p>

        <label htmlFor="free-side-choice" className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{msg('FE_FREE_SIDE_CHOOSE', 'Choose your free side')}</label>
        {sides.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            {msg('FE_FREE_SIDE_NONE_AVAILABLE', 'No free sides are available right now. Your credit stays on your account.')}
          </p>
        ) : (
          <select id="free-side-choice"
            value={choice?.id ?? ''}
            onChange={(e) => setChoiceId(e.target.value)}
            className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm font-semibold text-foreground bg-card focus:outline-none focus:border-primary/40"
          >
            {sides.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        )}

        {choice?.image_url && <img src={choice.image_url} alt={choice.name} className="mt-3 h-24 w-full rounded-xl object-cover" />}

        <div className="mt-4 space-y-2">
          <button
            onClick={handleUse}
            disabled={!choice || busy}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-[0.98] transition-transform disabled:opacity-50"
          >
            {busy ? msg('FE_FREE_SIDE_ADDING', 'Adding…') : msg('FE_FREE_SIDE_ADD', 'Add free side · ₦0 🏆')}
          </button>
          <button onClick={onClose} className="w-full py-2.5 rounded-full text-muted-foreground font-semibold text-xs">
            {msg('FE_FREE_SIDE_SKIP', 'Skip for now')}
          </button>
        </div>
      </motion.div>
    </div>
    </ModalPortal>
  );
}