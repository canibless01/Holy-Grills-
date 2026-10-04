import React, { useState, useRef, useEffect } from 'react';
import { CreditCard, Building2, X, Copy, Check, Flame, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { walletMinCardTopup, walletTopupMin, walletTopupHp } from '@/lib/appConfig';
import ModalPortal from '@/components/ModalPortal';

const PRESETS = [1000, 3000, 5000, 10000];

export default function WalletFundModal({ open, onClose, wallet, onSuccess }) {
  const [method, setMethod] = useState('card');
  const [amount, setAmount] = useState('');
  const [processing, setProcessing] = useState(false);
  const [bankWaiting, setBankWaiting] = useState(false);
  const [copied, setCopied] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setMethod('card'); setAmount(''); setProcessing(false); setBankWaiting(false);
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
  }, [open]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  if (!open) return null;

  const minTopup = walletMinCardTopup();
  const amt = parseFloat(amount);
  const valid = amt && amt >= minTopup;

  const startBankPoll = (startingBalance) => {
    setBankWaiting(true);
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const w = await liveApi.wallet.get();
        if ((w.balance || w.wallet_balance || 0) > (startingBalance || 0)) {
          clearInterval(pollRef.current); pollRef.current = null;
          setBankWaiting(false);
          onSuccess();
          onClose();
        }
      } catch { /* keep polling */ }
      if (attempts > 24) { clearInterval(pollRef.current); pollRef.current = null; setBankWaiting(false); }
    }, 5000);
  };

  const handleFund = async () => {
    if (!valid) return;
    setProcessing(true);
    try {
      if (method === 'card') {
        const result = await liveApi.wallet.fundCard({ amount: amt, callback_url: `${window.location.origin}/wallet` });
        if (result.authorization_url) {
          window.location.href = result.authorization_url;
          return;
        }
      } else {
        await liveApi.wallet.fundBank({ amount: amt });
        startBankPoll(wallet?.balance || wallet?.wallet_balance || 0);
      }
    } catch (e) {
      setProcessing(false);
      throw e;
    }
  };

  const copyAcct = () => {
    navigator.clipboard?.writeText(wallet?.virtual_account?.account_number || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !bankWaiting && !processing && onClose()}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-sm animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
          {bankWaiting ? (
            <div className="text-center py-4">
              <Loader2 className="w-10 h-10 text-success mx-auto mb-3 animate-spin" />
              <h3 className="font-heading font-bold text-foreground mb-1">Waiting for transfer</h3>
              <p className="text-xs text-muted-foreground mb-4 leading-relaxed">Send the exact amount to your virtual account. We'll confirm automatically once it lands.</p>
              <div className="p-4 rounded-2xl bg-muted mb-3">
                <div className="font-heading font-bold text-xl text-foreground tabular-nums">{wallet?.virtual_account?.account_number || '—'}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{wallet?.virtual_account?.bank_name || ''}</div>
                <button onClick={copyAcct} className="mt-2 inline-flex items-center gap-1 text-xs text-primary font-semibold">
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />} {copied ? 'Copied!' : 'Copy number'}
                </button>
              </div>
              <p className="text-xs text-success font-semibold animate-pulse">⏳ Listening for confirmation…</p>
              <button onClick={() => { if (pollRef.current) clearInterval(pollRef.current); setBankWaiting(false); }} className="mt-4 text-xs text-muted-foreground font-semibold">Cancel</button>
            </div>
          ) : (
            <>
              <div className="flex justify-between items-center mb-5">
                <h3 className="font-heading font-bold text-lg text-foreground">Fund Wallet</h3>
                <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary transition-colors"><X className="w-5 h-5 text-muted-foreground" /></button>
              </div>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2.5">
                  <button onClick={() => setMethod('card')} className={`p-3.5 rounded-2xl border-2 text-center transition-all ${method === 'card' ? 'border-primary/40 bg-primary/5' : 'border-border hover:border-input'}`}>
                    <CreditCard className={`w-5 h-5 mx-auto mb-1.5 ${method === 'card' ? 'text-primary' : 'text-foreground'}`} />
                    <span className="text-xs font-bold">Card</span>
                  </button>
                  <button onClick={() => setMethod('bank')} className={`p-3.5 rounded-2xl border-2 text-center transition-all ${method === 'bank' ? 'border-primary/40 bg-primary/5' : 'border-border hover:border-input'}`}>
                    <Building2 className={`w-5 h-5 mx-auto mb-1.5 ${method === 'bank' ? 'text-primary' : 'text-foreground'}`} />
                    <span className="text-xs font-bold">Bank Transfer</span>
                  </button>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Amount (min ₦{minTopup.toLocaleString()})</label>
                  <input
                    type="number"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="₦0"
                    className="w-full mt-1.5 p-3.5 rounded-2xl border border-border text-xl font-bold tabular-nums focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/20 transition-all"
                  />
                  <div className="grid grid-cols-4 gap-2 mt-2.5">
                    {PRESETS.map((a) => (
                      <button key={a} onClick={() => setAmount(String(a))} className={`py-2 rounded-xl text-xs font-bold transition-all active:scale-95 ${amount === String(a) ? 'bg-primary text-white' : 'bg-muted text-foreground hover:bg-secondary'}`}>
                        ₦{a >= 1000 ? `${a / 1000}k` : a}
                      </button>
                    ))}
                  </div>
                  {valid && (
                    <div className="flex items-center gap-1.5 mt-2.5 text-xs text-primary font-semibold">
                      <Flame className="w-3.5 h-3.5" /> You'll earn {walletTopupHp()} HP for topping up ₦{walletTopupMin().toLocaleString()}+!
                    </div>
                  )}
                </div>
                <button
                  onClick={handleFund}
                  disabled={processing || !valid}
                  className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm transition-all active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100"
                >
                  {processing ? 'Processing…' : `Fund ${amt ? formatNaira(amt) : 'Wallet'}`}
                </button>
                <p className="text-[10px] text-muted-foreground text-center leading-relaxed">
                  {method === 'card' ? "You'll be redirected to Paystack to pay securely." : "We'll confirm your transfer automatically via webhook."}
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </ModalPortal>
  );
}