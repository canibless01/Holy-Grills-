import { useState } from 'react';
import { X, Gift } from 'lucide-react';
import { motion } from 'framer-motion';
import { getFreeSideOptions } from '@/lib/featureConfig';
import ModalPortal from '@/components/ModalPortal';

// Checkout pop-up that appears when the user has free side credits. Lets them
// pick a side from free_side_options; the chosen side is added to the order at
// ₦0 and the credit is decremented server-side when the order is placed.
export default function FreeSideCreditModal({ open, count, onClose, onUse }) {
  const options = getFreeSideOptions();
  const [choice, setChoice] = useState(options[0] || '');

  if (!open || count <= 0) return null;

  const handleUse = () => {
    if (!choice) return;
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
        <select
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm font-semibold text-foreground bg-card focus:outline-none focus:border-primary/40"
        >
          {options.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>

        <div className="mt-4 space-y-2">
          <button
            onClick={handleUse}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-[0.98] transition-transform"
          >
            Add free side · ₦0 🏆
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