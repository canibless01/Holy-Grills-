import { GiftOptions } from '@/components/wallet/GiftOptions';
import { sessionStore } from '@/lib/storage';
import { useState, useEffect, useRef } from 'react';
import { Search, X, Send, Flame, AlertCircle, Check } from 'lucide-react';
import { useStudentSearch } from '@/hooks/useStudentSearch';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';
import { msg } from '@/lib/messages';
import { apiClient } from '@/lib/apiClient';
import { displayName, displayInitial } from '@/lib/displayName';
import { haptic } from '@/lib/haptic';

const DEFAULT_MIN_TRANSFER = 10;

/**
 * HpTransferModal — send Holy Points to another student.
 * Recipients are sourced from the live user-search endpoint
 * (GET /users/search?q=…), which is same-campus only and excludes the
 * searcher. The search is debounced so we only hit the API after the user
 * stops typing.
 */
export default function HpTransferModal({ open, onClose, initialRecipient = null }) {
  const { hpBalance, refreshHp, user, getSetting } = useHolyGrill();
  const configuredMinimum = getSetting('hp_transfer_min_amount', DEFAULT_MIN_TRANSFER);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [anonymous, setAnonymous] = useState(false);
  const [shareContact, setShareContact] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const requestRef = useRef<any>(null);
  const sendingRef = useRef(false);
  const pendingKey = `hg_pending_hp_gift_v1:${user?.id}`;
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const [showResults, setShowResults] = useState(false);

  const { results, searching, searchError, retry } = useStudentSearch(query, open && !selected);
  const [eligibility, setEligibility] = useState(null);
  const [eligibilityError, setEligibilityError] = useState('');
  useEffect(() => {
    if (!open) return;
    let active = true;
    setEligibility(null); setEligibilityError('');
    apiClient.get('/hp/transfer-eligibility').then((value) => { if (active) setEligibility(value); })
      .catch((failure) => { if (active) setEligibilityError(failure.message); });
    return () => { active = false; };
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery(initialRecipient?.name || ''); setSelected(initialRecipient ? { ...initialRecipient, full_name: initialRecipient.name } : null); setAmount(''); setNotes(initialRecipient ? 'Happy birthday!' : ''); setAnonymous(false); setShareContact(false); setUncertain(false); setError(null); setDone(null); setShowResults(false); requestRef.current = null;
      try {
        const saved = JSON.parse(sessionStore.getItem(pendingKey) || 'null');
        if (saved?.body?.request_id && saved?.recipient?.id && saved.body.recipient_id === saved.recipient.id) {
          requestRef.current = saved; setSelected(saved.recipient); setQuery(displayName(saved.recipient)); setAmount(String(saved.body.amount)); setNotes(saved.body.notes || ''); setAnonymous(saved.body.anonymous === true); setShareContact(saved.body.share_contact === true); setUncertain(true);
        }
      } catch { /* invalid storage cannot authorize a gift */ }
    }
  }, [open, initialRecipient, pendingKey]);

  if (!open) return null;

  const MIN_AMOUNT = eligibility?.minimum_amount ?? configuredMinimum;
  const activeHp = hpBalance?.active || 0;
  const amt = Number(amount);
  const amountValid = Number.isInteger(amt) && amt > 0 && amt >= MIN_AMOUNT && amt <= activeHp;

  const pickRecipient = (r) => { setSelected(r); setQuery(displayName(r)); setShowResults(false); };

  const handleSend = async () => {
    if (sendingRef.current) return;
    setError(null);
    if (!selected) { setError(msg('FE_HP_TRANSFER_MODAL_PICK_A_RECIPIENT_FIRST', 'Pick a recipient first.')); return; }
    if (selected.id === user?.id) { setError(msg('FE_HP_TRANSFER_MODAL_YOU_CAN_T_SEND_HP_TO_YOURSELF', 'You can\'t send HP to yourself.')); return; }
    if (!Number.isInteger(amt) || (!uncertain && amt < MIN_AMOUNT)) { setError(msg('FE_HP_TRANSFER_MODAL_MINIMUM_TRANSFER_IS_MIN_AMOUNT_HP', 'Minimum transfer is {min_amount} HP.', { min_amount: MIN_AMOUNT })); return; }
    if (!uncertain && amt > activeHp) { setError(msg('FE_HP_TRANSFER_MODAL_INSUFFICIENT_HP_BALANCE', 'Insufficient HP balance.')); return; }
    sendingRef.current = true; setSending(true);
    const details = { recipient_id: selected.id, amount: amt, notes: notes.trim(), anonymous, share_contact: shareContact };
    const fingerprint = JSON.stringify(details);
    if (!requestRef.current || requestRef.current.fingerprint !== fingerprint) requestRef.current = { fingerprint, body: { ...details, request_id: crypto.randomUUID() }, recipient: selected };
    sessionStore.setItem(pendingKey, JSON.stringify(requestRef.current));
    try {
      const res = await liveApi.hp.transfer(requestRef.current.body);
      sessionStore.removeItem(pendingKey); requestRef.current = null; setUncertain(false);
      try { await refreshHp(); } catch { /* a saved gift stays successful if the balance refresh fails */ }
      setDone({ amount: amt, name: res?.recipient_name || displayName(selected), newBalance: res?.new_balance });
      haptic('success');
      toast({
        title: msg('FE_HP_TRANSFER_MODAL_AMOUNT_HP_SENT', '🔥 {amount} HP sent!', { amount: amt }),
        description: msg('FE_HP_TRANSFER_MODAL_SENT_TO_NAME', 'Sent to {name}.', { name: res?.recipient_name || displayName(selected) }),
        sound: 'hp_transfer_sent',
      });
    } catch (e) {
      haptic('error');
      const failure = e?.message || 'Transfer failed.';
      setError(failure);
      if (e?.status === 400 || e?.status === 403) { sessionStore.removeItem(pendingKey); requestRef.current = null; setUncertain(false); }
      else setUncertain(true);
    }
    sendingRef.current = false; setSending(false);
  };

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-50 hg-scrim flex items-end sm:items-center justify-center p-4" onClick={() => { if (!sendingRef.current) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Send HP" className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {done ? (
          <div className="text-center py-4">
            <div className="w-14 h-14 rounded-full tone-success flex items-center justify-center mx-auto mb-3">
              <Check className="w-7 h-7 text-success" />
            </div>
            <h3 className="font-heading font-bold text-lg text-foreground">{done.amount} HP sent!</h3>
            <p className="text-sm text-muted-foreground mt-1">Sent to {done.name}.{done.newBalance != null && ` New balance: ${done.newBalance} HP.`}</p>
            <button onClick={onClose} className="mt-5 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Done</button>
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Flame className="w-5 h-5 text-primary" /> Send HP</h3>
              <button disabled={sending} aria-label="Close HP gift" onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>

            <div className="rounded-2xl bg-foreground p-3 text-white mb-4">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Available HP</div>
              <div className="font-heading font-extrabold text-2xl">{activeHp}</div>
            </div>

            <p role="status" className="text-xs text-muted-foreground mb-3">
              {eligibility ? `${eligibility.delivered_orders}/${eligibility.minimum_orders} delivered orders · ${eligibility.eligible ? 'Ready to send HP' : 'Complete more delivered orders to send HP'}` : eligibilityError || 'Checking transfer eligibility…'}
            </p>
            <fieldset disabled={sending || uncertain}>
            {/* Recipient search */}
            <label className="text-xs font-bold text-muted-foreground uppercase">Recipient</label>
            <div className="relative mt-1">
              <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSelected(null); setShowResults(true); }}
                onFocus={() => setShowResults(true)}
                placeholder="Search campus students by name or email…"
                className="w-full pl-9 pr-3 py-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/60"
              />
            </div>

            {showResults && query.trim() && (
              <div className="mt-2 max-h-40 overflow-y-auto space-y-1.5">
                {searching ? (
                  <p className="text-xs text-muted-foreground text-center py-2">Searching…</p>
                ) : searchError ? (
                  <button onClick={retry} className="text-xs text-destructive py-2">{searchError} Retry</button>
                ) : results.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-2">No students found for "{query.trim()}".</p>
                ) : (
                  results.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => pickRecipient(r)}
                      className={`w-full flex items-center gap-2 p-2.5 rounded-xl border text-left transition-all ${selected?.id === r.id ? 'border-primary/60 bg-primary/10' : 'border-border hover:border-input'}`}
                    >
                      <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center text-xs font-bold text-foreground">
                        {displayInitial(r)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-foreground truncate">{displayName(r)}</div>
                        {r.nickname && r.full_name && <div className="text-[10px] text-muted-foreground truncate">{r.full_name}</div>}
                      </div>
                      {selected?.id === r.id && <Check className="w-4 h-4 text-primary" />}
                    </button>
                  ))
                )}
              </div>
            )}

            {/* Amount */}
            <label className="text-xs font-bold text-muted-foreground uppercase mt-4 block">Amount (min {MIN_AMOUNT} HP)</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={`${MIN_AMOUNT}`}
              className="w-full mt-1 p-3 rounded-xl border border-border text-lg font-bold focus:outline-none focus:border-primary/60"
            />
            <div className="flex gap-2 mt-2">
              {[10, 25, 50, 100].map((a) => (
                <button key={a} onClick={() => setAmount(String(a))} className="flex-1 py-1.5 rounded-lg bg-muted text-xs font-bold text-foreground">{a}</button>
              ))}
            </div>

            <label className="text-xs font-bold text-muted-foreground uppercase mt-4 block">Note (optional)</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Treat yourself!"
              className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/60"
            />

            {eligibility?.gift_options_supported && <GiftOptions anonymous={anonymous} shareContact={shareContact} onAnonymous={setAnonymous} onShareContact={setShareContact} disabled={sending || uncertain} />}
            </fieldset>
            {uncertain && <p role="status" className="mt-3 text-xs text-muted-foreground">{msg('FE_GIFT_RECOVER_HINT', 'A response may have been lost. Retry this same gift before starting another; it keeps the same reference.')}</p>}
            {error && (
              <div className="flex items-center gap-2 mt-3 p-2.5 rounded-xl tone-error border border-destructive/30">
                <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
                <span className="text-xs text-destructive">{error}</span>
              </div>
            )}

            <button
              onClick={handleSend}
              disabled={sending || !selected || (!uncertain && (!amountValid || !eligibility?.eligible))}
              className="w-full mt-4 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {sending ? 'Sending…' : (<><Send className="w-4 h-4" /> Send{amt && !isNaN(amt) ? ` ${amt} HP` : ''}</>)}
            </button>
            <p className="text-[10px] text-muted-foreground text-center mt-2">HP comes from your active balance. The gift and notification are saved together.</p>
          </>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}