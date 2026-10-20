import { useState, useEffect } from 'react';
import { Truck, PackagePlus, Loader2, Check } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import type { RedemptionDeliveryChoicePayload } from '@/types/rewards';
import { msg } from '@/lib/messages';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";

/**
 * Post-fulfilment "How would you like this delivered?" flow.
 *
 * Opens immediately after a successful HP redemption. Two paths, both via
 * POST /rewards/redemptions/:id/delivery-choice { delivery_mode, ... }:
 *  - Deliver now (instant): records the choice; backend returns
 *    { delivery_mode, next_step: 'checkout', reward_redemption_id } — the
 *    caller then sends the user to checkout to place the reward order.
 *  - Add to my next order (next_order): backend returns
 *    { delivery_mode, message }. Available for food and simple physical rewards.
 *
 * Props: redemption { id, reward?: { fulfillment_type, menu_item_id } },
 * open, onClose, onDelivered(result|null).
 */
export default function RewardDeliveryModal({ redemption, open, onClose, onDelivered }) {
  const [mode, setMode] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setMode(null);
  }, [open, redemption?.id]);

  if (!open || !redemption) return null;


  const submit = async (chosenMode) => {
    setSubmitting(true);
    try {
      const body: RedemptionDeliveryChoicePayload = { delivery_mode: chosenMode };
      const res = await liveApi.rewards.chooseDelivery(redemption.id, body);
      if (chosenMode === 'next_order') {
        toast({ title: msg('FE_REWARD_DELIVERY_MODAL_ADDED_TO_YOUR_NEXT_ORDER', 'Added to your next order'), description: res?.message || 'Will attach to your next order.' });
        onClose();
        onDelivered?.(null);
      } else {
        // instant — backend records the choice and points to checkout; it does
        // NOT create the order here. Surface the backend message verbatim.
        toast({ title: msg('FE_REWARD_DELIVERY_MODAL_REWARD_READY_FOR_CHECKOUT', 'Reward ready for checkout'), description: res?.message || 'Continue to checkout to place your reward order.' });
        onClose();
        onDelivered?.(res);
      }
    } catch (e) {
      toast({ title: msg('FE_REWARD_DELIVERY_MODAL_DELIVERY_SETUP_FAILED', 'Delivery setup failed'), description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen && !submitting) onClose(); }}>
      <DialogContent className="max-w-sm rounded-3xl bg-card p-6">
        <div className="mb-2 pr-6">
          <DialogTitle>How would you like this delivered?</DialogTitle>
          <DialogDescription className="mt-1">{redemption?.reward?.name || redemption?.rewards?.name || redemption?.reward_name || 'Your reward'}</DialogDescription>
        </div>

        {/* Deliver now card */}
        <button
          type="button"
          disabled={submitting}
          onClick={() => setMode('instant')}
          className={`w-full text-left rounded-2xl border p-4 mb-3 transition ${mode === 'instant' ? 'border-primary bg-primary/5' : 'border-border'}`}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"><Truck className="w-5 h-5 text-primary" /></div>
            <div className="flex-1">
              <div className="font-bold text-sm text-foreground">Deliver now</div>
              <div className="text-[11px] text-muted-foreground">{msg('FE_REWARD_DELIVERY_LOCATION_FEE', 'Your reward is free. Choose your delivery location and review any delivery fee at checkout.')}</div>
            </div>
          </div>
        </button>

        {/* Attach the saved reward when the customer next orders. */}
        {(
          <button
            type="button"
            disabled={submitting}
            onClick={() => setMode('next_order')}
            className={`w-full text-left rounded-2xl border p-4 mb-3 transition ${mode === 'next_order' ? 'border-primary bg-primary/5' : 'border-border'}`}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center shrink-0"><PackagePlus className="w-5 h-5 text-success" /></div>
              <div className="flex-1">
                <div className="font-bold text-sm text-foreground">Add to my next order</div>
                <div className="text-[11px] text-muted-foreground">No extra fee — we'll attach it to your next order automatically.</div>
              </div>
            </div>
          </button>
        )}

        {mode && (
          <button
            onClick={() => submit(mode)}
            disabled={submitting}
            className="w-full mt-4 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Setting up…</> : mode === 'next_order' ? <><Check className="w-4 h-4" /> Confirm</> : <>Deliver now →</>}
          </button>
        )}
      </DialogContent>
    </Dialog>
  );
}