import React, { useState } from 'react';
import { X, Flame, Wallet, CreditCard, Split, Check, Loader2, Package } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';
import type { PurchaseListingPayload } from '@/types/marketplace';
import type { PaymentMethod } from '@/types/orders';

export default function PurchaseModal({ listing, onClose, onSuccess }) {
  const { hpBalance, wallet, refreshHp, refreshWallet } = useHolyGrill();
  const [method, setMethod] = useState('wallet');
  const [walletAmount, setWalletAmount] = useState(0);
  const [purchasing, setPurchasing] = useState(false);
  const [done, setDone] = useState(null);

  const cashPrice = listing.cash_price || listing.price;
  const hpPrice = listing.hp_price;
  const outOfStock = listing.is_out_of_stock || (listing.codes_remaining ?? listing.inventory_count) === 0;
  const walletBalance = wallet?.balance ?? wallet?.wallet_balance ?? 0;
  const activeHp = hpBalance?.active || 0;

  if (done) {
    return (
      <ModalPortal>
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={onClose}>
          <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-sm text-center animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-3">
              <Check className="w-8 h-8 text-success" />
            </div>
            <h3 className="font-heading font-bold text-lg text-foreground">{done.message || 'Purchase Successful!'}</h3>
            {done.code && done.code !== '—' ? (
              <p className="text-sm text-muted-foreground mt-2">Your code: <span className="font-mono font-bold text-primary">{done.code}</span></p>
            ) : (
              <p className="text-sm text-muted-foreground mt-2">Your order is being processed.</p>
            )}
            {done.hp_earned > 0 && (
              <div className="flex items-center justify-center gap-1 mt-2 text-primary font-bold text-sm">
                <Flame className="w-4 h-4" />+{done.hp_earned} HP earned
              </div>
            )}
            <button onClick={onSuccess} className="mt-5 w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm">Continue</button>
          </div>
        </div>
      </ModalPortal>
    );
  }

  const handlePurchase = async () => {
    setPurchasing(true);
    try {
      // 'hp' is the HP-discount option — backend only accepts payment_method
      // wallet/split (HP is a discount opt-in via use_hp, never a standalone method).
      const body: PurchaseListingPayload = { payment_method: (method === 'hp' ? 'wallet' : method) as PaymentMethod };
      if (method === 'hp') body.use_hp = true;
      if (method === 'split') body.wallet_amount = walletAmount;
      const res = await liveApi.marketplace.purchase(listing.id, body);

      if (res?.authorization_url) {
        window.location.href = res.authorization_url;
        return;
      }

      const purchase = res?.purchase || res?.data || res || {};
      const code = res?.code || purchase.code || purchase.voucher_code || purchase.redemption_code || '—';
      const hpEarned = res?.hp_earned || purchase.hp_earned || res?.hp_awarded || 0;
      await refreshHp();
      await refreshWallet();
      setDone({ code, hp_earned: hpEarned, message: res?.message });
    } catch (e) {
      toast({ title: 'Purchase failed', description: e.message, variant: 'destructive' });
    }
    setPurchasing(false);
  };

  const methods = [
    hpPrice != null && { key: 'hp', icon: Flame, color: 'text-primary', label: 'Pay with HP', sub: `${hpPrice} HP · You have ${activeHp}` },
    { key: 'wallet', icon: Wallet, color: 'text-success', label: 'Pay with Wallet', sub: `${formatNaira(cashPrice)} · Balance: ${formatNaira(walletBalance)}` },
    { key: 'card', icon: CreditCard, color: 'text-muted-foreground', label: 'Pay with Card', sub: `${formatNaira(cashPrice)} · Paystack` },
    { key: 'split', icon: Split, color: 'text-accent-foreground', label: 'Split (Wallet + Card)', sub: `${formatNaira(cashPrice)} total` },
  ].filter(Boolean);

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !purchasing && onClose()}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-sm animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-heading font-bold text-lg text-foreground">Choose Payment</h3>
            <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
          </div>

          {outOfStock && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-destructive/10 border border-destructive/20 mb-3">
              <Package className="w-4 h-4 text-destructive shrink-0" />
              <span className="text-xs font-semibold text-destructive">This item is out of stock.</span>
            </div>
          )}

          <div className="space-y-2">
            {methods.map((m) => (
              <button
                key={m.key}
                onClick={() => setMethod(m.key)}
                disabled={outOfStock}
                className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border-2 transition-all disabled:opacity-50 ${method === m.key ? 'border-primary/40 bg-primary/5' : 'border-border hover:border-input'}`}
              >
                <m.icon className={`w-5 h-5 ${m.color}`} />
                <div className="text-left flex-1 min-w-0">
                  <div className="font-semibold text-sm text-foreground">{m.label}</div>
                  <div className="text-xs text-muted-foreground truncate">{m.sub}</div>
                </div>
                {method === m.key && <Check className="w-4 h-4 text-primary shrink-0" />}
              </button>
            ))}

            {method === 'split' && (
              <div className="animate-slide-up p-3 rounded-xl bg-muted">
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Wallet Amount</label>
                <input
                  type="number"
                  value={walletAmount}
                  onChange={(e) => setWalletAmount(Math.min(walletBalance, Math.max(0, parseFloat(e.target.value) || 0)))}
                  max={walletBalance}
                  className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40 bg-card"
                />
                <p className="text-[10px] text-muted-foreground mt-1">Remaining {formatNaira(Math.max(0, cashPrice - walletAmount))} charged to card.</p>
              </div>
            )}

            <button
              onClick={handlePurchase}
              disabled={purchasing || outOfStock}
              className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50 mt-2"
            >
              {purchasing ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</> : `Confirm — ${formatNaira(cashPrice)}`}
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}