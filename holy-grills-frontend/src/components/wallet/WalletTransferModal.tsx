import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, Copy, Loader2, Send, ShieldCheck } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { sessionStore } from '@/lib/storage';
import { formatWalletMoney as formatNaira } from '@/lib/hgUtils';
import { Modal } from '@/components/admin/ui/AdminKit';

interface PendingTransfer {
  request_id: string;
  recipient_id: string;
  recipient_code: string;
  recipient_name: string;
  amount: number;
  note: string;
}
const DEFINITE_FAILURES = new Set(['account_unavailable', 'campus_required', 'transfers_paused', 'invalid_recipient_code',
  'recipient_unavailable', 'self_transfer', 'invalid_transfer', 'transfer_amount_out_of_range', 'transfer_daily_limit',
  'insufficient_wallet_balance', 'wallet_unavailable']);

export default function WalletTransferModal({ receiptId, onClose, onSuccess }: {
  receiptId?: string | null;
  onClose: () => void;
  onSuccess: () => void | Promise<void>;
}) {
  const { user } = useHolyGrill();
  const key = `hg_pending_wallet_transfer_v1:${user?.id}`;
  const [limits, setLimits] = useState<any>(null);
  const [recipient, setRecipient] = useState<any>(null);
  const [code, setCode] = useState('');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [pending, setPending] = useState<PendingTransfer | null>(null);
  const [receipt, setReceipt] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const guard = useRef(false);
  const success = useRef(onSuccess); success.current = onSuccess;

  const completed = async (value) => {
    setReceipt(value); setUncertain(false); setPending(null);
    const saved = sessionStore.getItem(key);
    try { if (saved && JSON.parse(saved).request_id === value.id) sessionStore.removeItem(key); } catch { /* no usable saved intent */ }
    try { await success.current(); } catch { /* receipt remains authoritative; Wallet can refresh separately */ }
  };

  useEffect(() => {
    let current = true;
    liveApi.wallet.getTransferLimits().then(value => { if (current) setLimits(value); })
      .catch(() => { if (current) setError('Transfer details could not be loaded. Close and try again.'); });
    let saved: PendingTransfer | null = null;
    try {
      const raw = sessionStore.getItem(key);
      if (raw) {
        const value = JSON.parse(raw);
        if (typeof value.request_id === 'string' && typeof value.recipient_id === 'string' &&
            typeof value.recipient_code === 'string' && Number.isFinite(value.amount) && value.amount > 0) saved = value;
      }
    } catch { /* malformed storage cannot authorize a transfer */ }
    if (saved) { setPending(saved); setUncertain(true); }
    const id = receiptId || saved?.request_id;
    if (id) {
      setBusy(true);
      liveApi.wallet.getTransfer(id).then(async result => { if (current) await completed(result.transfer); })
        .catch(() => { if (current) setError(saved ? 'This transfer is not confirmed yet. Check or retry this same transfer before creating another.' : 'This receipt could not be loaded for your account.'); })
        .finally(() => { if (current) setBusy(false); });
    }
    return () => { current = false; };
  }, [key, receiptId]); // eslint-disable-line react-hooks/exhaustive-deps

  const lookup = async (event) => {
    event.preventDefault(); if (guard.current) return;
    guard.current = true; setBusy(true); setError(''); setRecipient(null);
    try { const result = await liveApi.wallet.findTransferRecipient(code.trim()); setRecipient(result.recipient); }
    catch (err) { setError(err?.message || 'Recipient lookup failed. Please try again.'); }
    finally { guard.current = false; setBusy(false); }
  };
  const review = (event) => {
    event.preventDefault(); if (!recipient || !limits || !limits.enabled || guard.current) return;
    setError('');
    setPending({ request_id: crypto.randomUUID(), recipient_id: recipient.id, recipient_code: recipient.code,
      recipient_name: recipient.name, amount: Number(amount), note: note.trim() });
  };
  const send = async () => {
    if (!pending || guard.current) return;
    guard.current = true; setBusy(true); setError('');
    // Persist before the POST. Reloading, closing or losing its response must
    // recover this exact intent, never silently mint a second debit.
    sessionStore.setItem(key, JSON.stringify(pending));
    try {
      const result = await liveApi.wallet.sendTransfer(pending);
      await completed(result.transfer);
    } catch (err) {
      setError(err?.message || 'The transfer result is unknown. Check before sending again.');
      const failureCode = err?.detail?.code;
      if (DEFINITE_FAILURES.has(failureCode)) { sessionStore.removeItem(key); setUncertain(false); setPending(null); }
      else setUncertain(true);
    } finally { guard.current = false; setBusy(false); }
  };
  const check = async () => {
    const id = pending?.request_id || receiptId;
    if (!id || guard.current) return;
    guard.current = true; setBusy(true); setError('');
    try { const result = await liveApi.wallet.getTransfer(id); await completed(result.transfer); }
    catch { setError('No completed receipt could be confirmed yet. Keep checking or retry the same transfer below.'); }
    finally { guard.current = false; setBusy(false); }
  };
  const maximum = limits ? Math.min(limits.maximum_amount, limits.daily_remaining, limits.available_balance) : 0;
  const input = 'mt-1.5 w-full min-w-0 rounded-xl border border-border bg-background p-3 text-base outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:opacity-60';
  return <Modal open onClose={onClose} title={receipt ? 'Wallet transfer receipt' : 'Send wallet money'}>
    <div className="space-y-4" aria-busy={busy}>
      {error && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {receipt ? <>
        <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-success/10 text-success"><Check className="h-5 w-5" /></span><div><p className="text-xs text-muted-foreground">{receipt.direction === 'sent' ? 'Sent successfully' : 'Received successfully'}</p><p className="font-heading text-2xl font-extrabold">{formatNaira(receipt.amount)}</p></div></div>
        <dl className="space-y-3 rounded-2xl border border-border p-4 text-sm"><div><dt className="text-xs text-muted-foreground">From</dt><dd className="font-bold break-words">{receipt.sender_name}</dd></div><div><dt className="text-xs text-muted-foreground">To</dt><dd className="font-bold break-words">{receipt.recipient_name}</dd></div><div className="flex justify-between gap-3"><dt>Transfer fee</dt><dd className="font-bold">{formatNaira(0)}</dd></div><div className="flex justify-between gap-3"><dt>Balance after this transfer</dt><dd className="font-bold">{formatNaira(receipt.balance_after)}</dd></div>{receipt.note && <div><dt className="text-xs text-muted-foreground">Note</dt><dd className="break-words">{receipt.note}</dd></div>}<div><dt className="text-xs text-muted-foreground">Date</dt><dd>{new Date(receipt.created_at).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })} WAT</dd></div><div><dt className="text-xs text-muted-foreground">Reference</dt><dd className="break-all font-mono text-xs">{receipt.id}</dd></div></dl>
        <button onClick={onClose} className="w-full rounded-xl bg-gradient-cta p-3 font-bold text-white">Done</button>
      </> : pending ? <>
        <p className="text-sm font-semibold">{uncertain ? 'Check this transfer' : 'Review your transfer'}</p>
        <div className="rounded-2xl bg-brand-brown p-4 text-white"><p className="text-xs text-white/70">You are sending</p><p className="mt-1 text-3xl font-extrabold">{formatNaira(pending.amount)}</p><p className="mt-3 font-bold break-words">To {pending.recipient_name}</p><p className="text-xs text-white/70">Code: {pending.recipient_code} · Same campus</p></div>
        <p className="text-sm">Transfer fee: <strong>{formatNaira(0)}</strong>. Your friend can spend the money immediately. Please check the recipient carefully before confirming.</p>
        {pending.note && <p className="rounded-xl bg-background p-3 text-sm break-words">{pending.note}</p>}
        {uncertain && <><p role="status" className="text-sm text-muted-foreground">A response may have been lost after the money moved. Closing this page keeps the same reference for recovery.</p><button disabled={busy} onClick={check} className="w-full rounded-xl border border-primary p-3 font-bold text-primary disabled:opacity-50">Check transfer</button></>}
        <button disabled={busy} onClick={send} className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-cta p-3 font-bold text-white disabled:opacity-50">{busy ? <><Loader2 className="h-4 w-4 animate-spin" />Checking…</> : uncertain ? 'Retry this same transfer' : <>Send {formatNaira(pending.amount)}<ArrowRight className="h-4 w-4" /></>}</button>
        {!uncertain && <button disabled={busy} onClick={() => setPending(null)} className="w-full py-2 text-sm font-semibold">Edit details</button>}
      </> : receiptId ? <button disabled={busy} onClick={check} className="w-full rounded-xl border border-border p-3 font-bold">{busy ? 'Loading receipt…' : 'Retry receipt'}</button> : !limits ? <p role="status" className="py-3 text-sm text-muted-foreground">Loading your transfer details…</p> : !limits.enabled ? <p role="status" className="text-sm">Wallet transfers are currently paused. Your wallet balance remains available to spend.</p> : <>
        <div className="rounded-2xl bg-success p-4 text-white"><p className="text-xs text-white/75">Available wallet balance</p><p className="mt-1 text-2xl font-extrabold">{formatNaira(limits.available_balance)}</p></div>
        {limits.my_code && <div className="flex items-center justify-between gap-3 rounded-xl bg-background p-3 text-xs"><span>Your code: <strong className="font-mono">{limits.my_code}</strong></span><button aria-label="Copy my referral code" onClick={async () => { try { await navigator.clipboard.writeText(limits.my_code); setCopied(true); } catch { setError('Copy is unavailable. You can select your code instead.'); } }} className="flex items-center gap-1.5 font-bold text-primary"><Copy className="h-3.5 w-3.5" />{copied ? 'Copied' : 'Copy'}</button></div>}
        <form onSubmit={lookup} className="space-y-3"><label className="block text-sm font-bold">Friend’s referral code<input className={input} required pattern="[A-Za-z0-9_-]{3,80}" maxLength={80} value={code} onChange={event => { setCode(event.target.value.toUpperCase()); setRecipient(null); }} placeholder="Enter their referral code" disabled={busy} /></label><p className="text-xs text-muted-foreground">Ask your friend for the code on their Referrals page. You can send to active accounts on your campus.</p><button disabled={busy} className="w-full rounded-xl border border-border p-3 text-sm font-bold disabled:opacity-50">{busy ? 'Checking…' : 'Find recipient'}</button></form>
        {recipient && <form onSubmit={review} className="space-y-4 border-t border-border pt-4"><div className="rounded-xl bg-success/5 p-3"><p className="font-bold break-words">{recipient.name}</p><p className="mt-0.5 font-mono text-xs text-muted-foreground">{recipient.code} · Same campus</p></div><label className="block text-sm font-bold">Amount (₦)<input className={input} type="number" inputMode="decimal" required min={limits.minimum_amount} max={maximum} step="0.01" value={amount} onChange={event => setAmount(event.target.value)} disabled={busy} /></label><p className="text-xs text-muted-foreground">Minimum {formatNaira(limits.minimum_amount)} · Up to {formatNaira(Math.max(0, maximum))} available to send today.</p><label className="block text-sm font-bold">Note (optional)<input className={input} maxLength={200} value={note} onChange={event => setNote(event.target.value)} disabled={busy} /></label><button disabled={busy || maximum < limits.minimum_amount} className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-cta p-3 font-bold text-white disabled:opacity-50"><Send className="h-4 w-4" />Review transfer</button></form>}
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><ShieldCheck className="h-3.5 w-3.5 shrink-0" />No transfer fee. Wallet money stays within Holy Grills.</p>
      </>}
    </div>
  </Modal>;
}
