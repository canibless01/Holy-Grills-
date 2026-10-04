import { useState, useEffect } from 'react';
import { X, Truck, PackagePlus, MapPin, Loader2, Check } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import type { RedemptionDeliveryChoicePayload } from '@/types/rewards';
import { msg } from '@/lib/messages';

/**
 * Post-fulfilment "How would you like this delivered?" flow.
 *
 * Opens after an admin sets a redemption to `fulfilled`. Two paths, both via
 * POST /rewards/redemptions/:id/delivery-choice { delivery_mode, ... }:
 *  - Deliver now (instant): records the choice; backend returns
 *    { delivery_mode, next_step: 'checkout', reward_redemption_id } — the
 *    caller then sends the user to checkout to place the reward order.
 *  - Add to my next order (next_order): backend returns
 *    { delivery_mode, message }. Only offered for menu_item rewards — simple
 *    rewards (merch/vouchers) deliver now only.
 *
 * Props: redemption { id, reward?: { fulfillment_type, menu_item_id } },
 * open, onClose, onDelivered(result|null).
 */
export default function RewardDeliveryModal({ redemption, open, onClose, onDelivered }) {
  const [addresses, setAddresses] = useState([]);
  const [addressId, setAddressId] = useState('');
  const [deliveryType, setDeliveryType] = useState('delivery');
  const [mode, setMode] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMode(null);
    setAddressId('');
    setDeliveryType('delivery');
    liveApi.addresses.list().then((a) => {
      const list = Array.isArray(a) ? a : (a?.addresses || []);
      setAddresses(list);
      if (list.length) setAddressId(list[0].id);
    }).catch(() => {});
  }, [open]);

  if (!open || !redemption) return null;

  const fulfillmentType = redemption?.reward?.fulfillment_type || redemption?.fulfillment_type || 'menu_item';
  const isSimple = fulfillmentType === 'simple';

  const submit = async (chosenMode) => {
    setSubmitting(true);
    try {
      const body: RedemptionDeliveryChoicePayload = { delivery_mode: chosenMode };
      if (chosenMode === 'instant') {
        body.delivery_location_id = addressId || undefined;
        body.delivery_type = deliveryType;
        body.menu_item_id_for_reward = redemption?.reward?.menu_item_id || redemption?.menu_item_id_for_reward || undefined;
      }
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

  const instantBlocked = mode === 'instant' && addresses.length > 0 && !addressId;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="font-heading font-bold text-lg text-foreground">How would you like this delivered?</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{redemption?.reward?.name || redemption?.reward_name || 'Your reward'}</p>
          </div>
          <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
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
              <div className="text-[11px] text-muted-foreground">Standard delivery fee applies — we'll prepare and send it right away.</div>
            </div>
          </div>
        </button>

        {/* Add to next order card — menu-item rewards only */}
        {!isSimple && (
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

        {isSimple && (
          <p className="text-[11px] text-muted-foreground mb-3">Simple rewards (merch, vouchers) are delivered right away — there's no next-order option.</p>
        )}

        {/* Instant-mode detail form */}
        {mode === 'instant' && (
          <div className="space-y-3 animate-fade-in">
            {addresses.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">No saved addresses. Add one in Addresses to deliver now, or choose "Add to my next order" if available.</p>
            ) : (
              <>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide flex items-center gap-1 mb-1"><MapPin className="w-3 h-3" /> Delivery address</label>
                  <select value={addressId} onChange={(e) => setAddressId(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm bg-card">
                    {addresses.map((a) => <option key={a.id} value={a.id}>{a.label || a.name || a.address || `Address ${String(a.id).slice(0, 4)}`}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide mb-1 block">Delivery type</label>
                  <select value={deliveryType} onChange={(e) => setDeliveryType(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm bg-card">
                    <option value="delivery">Delivery</option>
                    <option value="pickup">Pickup</option>
                  </select>
                </div>
              </>
            )}
          </div>
        )}

        {mode && (
          <button
            onClick={() => submit(mode)}
            disabled={submitting || instantBlocked}
            className="w-full mt-4 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Setting up…</> : mode === 'next_order' ? <><Check className="w-4 h-4" /> Confirm</> : <>Deliver now →</>}
          </button>
        )}
      </div>
    </div>
  );
}