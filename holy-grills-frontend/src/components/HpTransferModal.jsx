import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Send, Flame, AlertCircle, Check } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';

const DEFAULT_MIN_TRANSFER = 10;

/**
 * HpTransferModal — send Holy Points to another student.
 * Recipients are sourced from the live user-search endpoint
 * (GET /users/search?q=…), which is same-campus only and excludes the
 * searcher. The search is debounced so we only hit the API after the user
 * stops typing.
 */
export default function HpTransferModal({ open, onClose }) {
  const { hpBalance, refreshHp, user, getSetting } = useHolyGrill();
  const MIN_AMOUNT = getSetting('hp_transfer_min_amount', DEFAULT_MIN_TRANSFER);
  const [results, setResults] = useState([]);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [sending, setSending] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const debounceRef = useRef(null);
  const [showResults, setShowResults] = useState(false);

  // Debounced search — hit /users/search 350ms after the user stops typing.
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (!q) { setResults([]); setSearching(false); return; }
    setSearching(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await liveApi.users.search({ q });
        setResults(Array.isArray(res) ? res : []);
      } catch { setResults([]); }
      setSearching(false);
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, open]);

  useEffect(() => {
    if (open) {
      setQuery(''); setSelected(null); setAmount(''); setNotes(''); setError(null); setDone(null); setResults([]); setShowResults(false);
    }
  }, [open]);

  if (!open) return null;

  const activeHp = hpBalance?.active || 0;
  const amt = parseInt(amount, 10);
  const amountValid = !isNaN(amt) && amt >= MIN_AMOUNT && amt <= activeHp;

  const pickRecipient = (r) => { setSelected(r); setQuery(r.full_name); setShowResults(false); };

  const handleSend = async () => {
    setError(null);
    if (!selected) { setError('Pick a recipient first.'); return; }
    if (selected.id === user?.id) { setError('You can\'t send HP to yourself.'); return; }
    if (isNaN(amt) || amt < MIN_AMOUNT) { setError(`Minimum transfer is ${MIN_AMOUNT} HP.`); return; }
    if (amt > activeHp) { setError('Insufficient HP balance.'); return; }
    setSending(true);
    try {
      const res = await liveApi.hp.transfer({ recipient_id: selected.id, amount: amt, notes: notes.trim() || undefined });
      await refreshHp();
      setDone({ amount: amt, name: res?.recipient_name || selected.full_name, newBalance: res?.new_balance });
      toast({ title: `🔥 ${amt} HP sent!`, description: `Sent to ${res?.recipient_name || selected.full_name}.`, sound: 'hp_transfer_sent' });
    } catch (e) {
      const msg = e?.message || 'Transfer failed.';
      setError(msg);
    }
    setSending(false);
  };

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {done ? (
          <div className="text-center py-4">
            <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
              <Check className="w-7 h-7 text-green-600" />
            </div>
            <h3 className="font-heading font-bold text-lg text-foreground">{done.amount} HP sent!</h3>
            <p className="text-sm text-muted-foreground mt-1">Sent to {done.name}.{done.newBalance != null && ` New balance: ${done.newBalance} HP.`}</p>
            <button onClick={onClose} className="mt-5 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Done</button>
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Flame className="w-5 h-5 text-primary" /> Send HP</h3>
              <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>

            <div className="rounded-2xl bg-foreground p-3 text-white mb-4">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Available HP</div>
              <div className="font-heading font-extrabold text-2xl">{activeHp}</div>
            </div>

            {/* Recipient search */}
            <label className="text-xs font-bold text-muted-foreground uppercase">Recipient</label>
            <div className="relative mt-1">
              <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSelected(null); setShowResults(true); }}
                onFocus={() => setShowResults(true)}
                placeholder="Search by name or username…"
                className="w-full pl-9 pr-3 py-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/60"
              />
            </div>

            {showResults && query.trim() && (
              <div className="mt-2 max-h-40 overflow-y-auto space-y-1.5">
                {searching ? (
                  <p className="text-xs text-muted-foreground text-center py-2">Searching…</p>
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
                        {(r.full_name || r.nickname || '?').charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-foreground truncate">{r.full_name || r.nickname}</div>
                        {r.nickname && r.full_name && <div className="text-[10px] text-muted-foreground truncate">@{r.nickname}</div>}
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

            {error && (
              <div className="flex items-center gap-2 mt-3 p-2.5 rounded-xl bg-red-50 border border-red-200">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span className="text-xs text-red-800">{error}</span>
              </div>
            )}

            <button
              onClick={handleSend}
              disabled={sending || !selected || !amountValid}
              className="w-full mt-4 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {sending ? 'Sending…' : (<><Send className="w-4 h-4" /> Send{amt && !isNaN(amt) ? ` ${amt} HP` : ''}</>)}
            </button>
            <p className="text-[10px] text-muted-foreground text-center mt-2">HP comes from your Active balance. Recipients are notified instantly.</p>
          </>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}