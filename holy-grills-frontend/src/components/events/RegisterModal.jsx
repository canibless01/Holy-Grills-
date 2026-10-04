import React, { useState } from 'react';
import { ChevronLeft, Wallet, CreditCard, Flame, Check, Loader2, Tag, Info } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';

// Spec-aligned event registration modal.
// Guests  → card-only, guest_name/guest_email/guest_phone + dynamic fields.
// Authed  → wallet / card / split + opt-in HP toggle (use_hp), wallet_amount
//           for split, promo_code, dynamic registration_fields → registration_answers.
// Card payments redirect to Paystack (authorization_url); the UI must not
// promise instant confirmation for card — it polls after return.
export default function RegisterModal({ event, tiers, user, wallet, hpBalance, isAuthenticated, onClose, onSuccess }) {
  const isGuest = !isAuthenticated;
  const [selectedTier, setSelectedTier] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState(isGuest ? 'card' : 'wallet');
  const [useHp, setUseHp] = useState(false);
  const [walletAmount, setWalletAmount] = useState('');
  const [promoCode, setPromoCode] = useState('');
  const [guest, setGuest] = useState({
    guest_name: user?.full_name || '',
    guest_email: user?.email || '',
    guest_phone: user?.phone || '',
  });
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const regFields = Array.isArray(event?.registration_fields) ? event.registration_fields : [];
  const price = selectedTier ? (selectedTier.price_naira ?? 0) : (event?.ticket_price ?? 0);
  const hpPrice = selectedTier ? (selectedTier.price_hp ?? 0) : (event?.hp_required ?? 0);
  const walletBalance = wallet?.balance ?? wallet?.wallet_balance ?? 0;
  const activeHp = hpBalance?.active || 0;
  const hpAvailable = !isGuest && (event?.hp_promo_enabled || hpPrice > 0);
  const isFree = price === 0 && hpPrice === 0;

  const setGuestField = (k) => (e) => setGuest({ ...guest, [k]: e.target.value });
  const setAnswer = (name, value) => setAnswers((a) => ({ ...a, [name]: value }));

  // Dynamic registration-field validation + guest field validation.
  const guestValid = isGuest
    ? (guest.guest_name.trim() && /\S+@\S+\.\S+/.test(guest.guest_email) && guest.guest_phone.trim())
    : true;
  const tierValid = tiers.length === 0 || !!selectedTier;
  const fieldsValid = regFields.every((f) => !f.required || (answers[f.name] != null && String(answers[f.name]).trim() !== ''));
  const splitValid = paymentMethod !== 'split' || (Number(walletAmount) > 0 && Number(walletAmount) < price);
  const valid = guestValid && tierValid && fieldsValid && splitValid && (isFree || paymentMethod);

  const handleRegister = async () => {
    setSubmitting(true);
    try {
      const body = { callback_url: window.location.href };
      if (selectedTier) body.tier_id = selectedTier.id;
      if (promoCode.trim()) body.promo_code = promoCode.trim();
      body.registration_answers = answers;

      if (isGuest) {
        body.guest_name = guest.guest_name.trim();
        body.guest_email = guest.guest_email.trim();
        body.guest_phone = guest.guest_phone.trim();
      } else {
        body.payment_method = paymentMethod;
        body.use_hp = !!useHp;
        if (paymentMethod === 'split') body.wallet_amount = Number(walletAmount) || 0;
      }

      const res = await liveApi.events.register(event.id, body);

      // Card payments are webhook-driven — redirect to Paystack and poll after.
      if (res?.authorization_url) {
        window.location.href = res.authorization_url;
        return;
      }

      const t = res?.data || res || {};
      const ticketId = t.ticket_id || t.id || t.ticket?.id || '—';
      onSuccess({ ...t, ticket_id: ticketId, tier_name: selectedTier?.name, guest_email: isGuest ? guest.guest_email.trim() : null });
      toast({
        title: '✅ Ticket secured!',
        description: selectedTier ? `Your ${selectedTier.name} ticket is confirmed.` : 'Your ticket is confirmed.',
      });
    } catch (e) {
      toast({ title: 'Registration failed', description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  // Payment methods — guests are card-only (spec §11.4).
  const methods = isGuest
    ? [{ key: 'card', icon: CreditCard, color: 'text-muted-foreground', label: 'Card', sub: `${formatNaira(price)} · Paystack` }]
    : [
        { key: 'wallet', icon: Wallet, color: 'text-success', label: 'Wallet', sub: `${formatNaira(price)} · Bal: ${formatNaira(walletBalance)}` },
        ...(walletBalance > 0 && price > 0 ? [{ key: 'split', icon: Wallet, color: 'text-accent', label: 'Split', sub: 'Wallet + Card' }] : []),
        { key: 'card', icon: CreditCard, color: 'text-muted-foreground', label: 'Card', sub: `${formatNaira(price)} · Paystack` },
      ];

  const renderField = (f) => {
    const name = f.name || f.key;
    const label = f.label || f.name;
    const val = answers[name] ?? '';
    const base = "w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40";
    if (f.type === 'select') {
      return (
        <select key={name} value={val} onChange={(e) => setAnswer(name, e.target.value)} className={base}>
          <option value="">{f.placeholder || `Select ${label}`}</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }
    if (f.type === 'checkbox') {
      return (
        <label key={name} className="flex items-center gap-2 p-3 rounded-xl border border-border text-sm">
          <input type="checkbox" checked={!!val} onChange={(e) => setAnswer(name, e.target.checked)} className="w-4 h-4 accent-[var(--primary)]" />
          <span className="text-foreground">{label}{f.required ? ' *' : ''}</span>
        </label>
      );
    }
    if (f.type === 'textarea') {
      return <textarea key={name} value={val} onChange={(e) => setAnswer(name, e.target.value)} placeholder={`${label}${f.required ? ' *' : ''}`} rows={2} className={base} />;
    }
    return (
      <input
        key={name}
        type={f.type === 'number' ? 'number' : f.type === 'email' ? 'email' : 'text'}
        value={val}
        onChange={(e) => setAnswer(name, e.target.value)}
        placeholder={`${label}${f.required ? ' *' : ''}`}
        className={base}
      />
    );
  };

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !submitting && onClose()}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-md max-h-[90vh] overflow-y-auto animate-slide-up" onClick={(e) => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-heading font-bold text-lg text-foreground">{isFree ? 'Register for this event' : 'Get Your Ticket'}</h3>
            <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary"><ChevronLeft className="w-5 h-5 text-muted-foreground" /></button>
          </div>

          <div className="space-y-4">
            {isGuest && !isFree && (
              <div className="rounded-xl bg-accent/10 border border-accent/20 p-3 flex gap-2 items-start">
                <Info className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <p className="text-xs text-foreground">Guest tickets are card-only. Create an account to pay with wallet, split, or HP.</p>
              </div>
            )}

            {!isGuest && (
              <div className="rounded-xl bg-accent/10 border border-accent/20 p-3 flex gap-2 items-start">
                <Info className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <p className="text-xs text-foreground">
                  Registering as <span className="font-bold">{user?.full_name || 'your account'}</span>
                  {user?.email ? ` (${user.email})` : ''} — your details come from your account, so there's nothing to type.
                </p>
              </div>
            )}

            {tiers.length > 0 && (
              <div>
                <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Select a tier</div>
                <div className="grid grid-cols-2 gap-2">
                  {tiers.map((t) => {
                    const remaining = (t.capacity ?? 0) - (t.sold_count ?? 0);
                    const soldOut = remaining <= 0;
                    const selected = selectedTier?.id === t.id;
                    return (
                      <button
                        key={t.id}
                        onClick={() => !soldOut && setSelectedTier(t)}
                        disabled={soldOut}
                        className={`p-3 rounded-2xl border-2 text-left transition-all ${selected ? 'border-primary bg-primary/5' : 'border-border'} ${soldOut ? 'opacity-50' : 'active:scale-95'}`}
                      >
                        <div className="font-bold text-sm text-foreground">{t.name}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">{formatNaira(t.price_naira ?? 0)}{t.price_hp ? ` · ${t.price_hp} HP` : ''}</div>
                        <div className={`text-[10px] font-semibold mt-1 ${remaining <= 5 ? 'text-destructive' : 'text-success'}`}>
                          {soldOut ? 'Sold out' : `${remaining} left`}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {isGuest && (
              <div>
                <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Your details</div>
                <div className="space-y-2">
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Full name *" value={guest.guest_name} onChange={setGuestField('guest_name')} />
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Email *" type="email" value={guest.guest_email} onChange={setGuestField('guest_email')} />
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Phone *" value={guest.guest_phone} onChange={setGuestField('guest_phone')} />
                </div>
              </div>
            )}

            {regFields.length > 0 && (
              <div>
                <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Additional info</div>
                <div className="space-y-2">
                  {regFields.map(renderField)}
                </div>
              </div>
            )}

            {!isFree && (
              <>
                <div>
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Pay with</div>
                  <div className="space-y-2">
                    {methods.map((m) => (
                      <button
                        key={m.key}
                        onClick={() => setPaymentMethod(m.key)}
                        className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border-2 transition-all ${paymentMethod === m.key ? 'border-primary/40 bg-primary/5' : 'border-border hover:border-input'}`}
                      >
                        <m.icon className={`w-5 h-5 ${m.color}`} />
                        <div className="text-left flex-1 min-w-0">
                          <div className="font-semibold text-sm text-foreground">{m.label}</div>
                          <div className="text-xs text-muted-foreground truncate">{m.sub}</div>
                        </div>
                        {paymentMethod === m.key && <Check className="w-4 h-4 text-primary shrink-0" />}
                      </button>
                    ))}
                  </div>
                </div>

                {paymentMethod === 'split' && (
                  <div>
                    <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Wallet amount (rest on card)</div>
                    <input
                      type="number"
                      min="1"
                      max={price - 1}
                      value={walletAmount}
                      onChange={(e) => setWalletAmount(e.target.value)}
                      placeholder={`Max ${formatNaira(Math.max(0, price - 1))}`}
                      className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40"
                    />
                  </div>
                )}

                {hpAvailable && (
                  <button
                    onClick={() => setUseHp((v) => !v)}
                    className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border-2 transition-all ${useHp ? 'border-primary/40 bg-primary/5' : 'border-border'}`}
                  >
                    <Flame className={`w-5 h-5 ${useHp ? 'text-primary' : 'text-muted-foreground'}`} />
                    <div className="text-left flex-1 min-w-0">
                      <div className="font-semibold text-sm text-foreground">Use {hpPrice} HP discount?</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {useHp && activeHp < hpPrice
                          ? `Insufficient HP — you'll pay full price (${formatNaira(price)})`
                          : `Opt in to apply HP. You have ${activeHp} HP.`}
                      </div>
                    </div>
                    <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${useHp ? 'bg-primary border-primary' : 'border-border'}`}>
                      {useHp && <Check className="w-3.5 h-3.5 text-white" />}
                    </div>
                  </button>
                )}

                <div>
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide mb-2">Promo code (optional)</div>
                  <div className="relative">
                    <Tag className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      value={promoCode}
                      onChange={(e) => setPromoCode(e.target.value)}
                      placeholder="Enter code"
                      className="w-full pl-9 pr-3 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40"
                    />
                  </div>
                </div>
              </>
            )}

            <button
              onClick={handleRegister}
              disabled={submitting || !valid}
              className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50"
            >
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Processing…</> : (isFree ? 'Confirm registration' : 'Confirm and pay')}
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}