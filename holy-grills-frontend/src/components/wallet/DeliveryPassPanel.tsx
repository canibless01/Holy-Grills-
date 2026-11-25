import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Check, CreditCard, RefreshCw, ShieldCheck, Truck, Wallet } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';
import { passDate, passStatus } from '@/lib/deliveryPass';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';

const methods = [{ value: 'wallet', Icon: Wallet, key: 'FE_PASS_WALLET', fallback: 'Wallet' }, { value: 'card', Icon: CreditCard, key: 'FE_PASS_CARD', fallback: 'Card' }];

const primary = 'flex min-h-12 w-full items-center justify-center gap-2 rounded-full bg-gradient-cta px-5 text-sm font-extrabold text-white disabled:opacity-50';
const secondary = 'min-h-11 rounded-full border border-border px-4 text-sm font-bold disabled:opacity-50';

export default function DeliveryPassPanel({ callbackId, onPaid }: { callbackId?: string | null; onPaid?: () => Promise<void> }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(!!callbackId);
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState('wallet');
  const [renew, setRenew] = useState(false);
  const [proof, setProof] = useState<any>(null);
  const lock = useRef(false);
  const alive = useRef(true);
  const generation = useRef(0);
  const callbackSeen = useRef(new Set<string>());
  const paidSeen = useRef(new Set<string>());
  const intent = useCmsCreateIntent();
  const reload = async () => {
    const version = ++generation.current;
    const value = await apiClient.get('/delivery-pass');
    if (alive.current && version === generation.current) { setData(value); setError(''); if (!value.renewals_ready) setRenew(false); }
    return value;
  };
  useEffect(() => {
    alive.current = true;
    void reload().catch(failure => { if (alive.current) setError(failure.message); });
    return () => { alive.current = false; generation.current++; };
  }, []);
  const settle = async (receipt) => {
    if (!alive.current) return;
    if (['paid', 'credited', 'refunded'].includes(receipt?.status)) {
      setProof(receipt); intent.clear();
      if (!paidSeen.current.has(receipt.id)) {
        paidSeen.current.add(receipt.id);
        try { await onPaid?.(); } catch { /* Payment remains saved if the wallet refresh fails. */ }
      }
    }
    if (receipt?.status === 'failed') intent.clear();
  };
  const verify = async (id) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const result = await apiClient.post(`/delivery-pass/receipts/${id}/verify`, {});
      await settle(result.receipt); await reload();
    } catch (failure) { if (alive.current) setError(failure.message); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  };
  useEffect(() => {
    if (!callbackId) return;
    setOpen(true);
    if (/^[0-9a-f-]{36}$/i.test(callbackId) && !callbackSeen.current.has(callbackId)) {
      callbackSeen.current.add(callbackId); void verify(callbackId);
    }
  }, [callbackId]);
  const pendingId = data?.pending?.id;
  useEffect(() => {
    if (!open || !pendingId) return;
    let count = 0;
    const check = () => { if (!document.hidden && count++ < 4) void verify(pendingId); };
    const timer = window.setInterval(check, 15000);
    window.addEventListener('focus', check);
    return () => { clearInterval(timer); window.removeEventListener('focus', check); };
  }, [open, pendingId]);
  const run = async (operation, options: { cancelled?: boolean } = {}) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const result = await operation();
      if (!alive.current) return;
      if (options.cancelled) { intent.clear(); setProof(null); }
      await settle(result.receipt);
      if (result.membership) setRenew(false);
      const receipt = result.receipt;
      if (receipt?.status === 'pending' && receipt.checkout_url?.startsWith('https://checkout.paystack.com/')) {
        window.location.assign(receipt.checkout_url); return;
      }
      await reload();
    } catch (failure) { if (alive.current) setError(failure.message); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  };
  if (!data && !error) return null;
  if (data && !data.available && !data.membership && !data.pending && !data.history?.length && !callbackId) return null;
  const membership = data?.membership;
  const active = membership?.active === true || proof?.status === 'paid' && new Date(proof.period_until).getTime() > Date.now();
  const until = membership?.active ? membership.paid_until : proof?.period_until;
  const price = (membership?.active ? membership.price_kobo : data?.offer?.price_kobo || 0) / 100;
  const pending = data?.pending;
  const pendingExpired = pending && new Date(pending.expires_at).getTime() <= Date.now();
  const reloadSafe = () => { void reload().catch(failure => setError(failure.message)); };
  return <>
    <section className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent/20 text-brand-brown"><Truck className="h-5 w-5" /></span>
      <div className="min-w-0 flex-1"><h2 className="font-heading text-base font-extrabold">{msg('FE_PASS_TITLE', 'Delivery pass')}</h2><p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{active ? msg('FE_PASS_ACTIVE_UNTIL', 'Delivery covered until {date}', { date: passDate(until) }) : pending ? msg('FE_PASS_PENDING', 'Payment awaiting confirmation') : data?.available ? `${formatNaira(price)} ${msg('FE_PASS_MONTH', 'per month')}` : msg('FE_PASS_UNAVAILABLE', 'Currently unavailable')}</p></div>
      <button type="button" className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-bold" onClick={() => setOpen(true)}>{active || pending ? msg('FE_PASS_MANAGE', 'Manage pass') : msg('FE_PASS_EXPLORE', 'See delivery pass')}<ArrowUpRight className="h-3.5 w-3.5" /></button>
    </section>
    <Dialog open={open} onOpenChange={value => { if (!lock.current) setOpen(value); }}><DialogContent className="max-h-[90dvh] w-[calc(100%_-_2rem)] overflow-y-auto rounded-3xl p-5 sm:p-7">
      <div><span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/20 text-brand-brown"><Truck className="h-6 w-6" /></span><DialogTitle className="font-heading text-2xl font-extrabold">{msg('FE_PASS_TITLE', 'Delivery pass')}</DialogTitle><DialogDescription className="mt-2 text-sm leading-relaxed">{msg('FE_PASS_COVERAGE', 'Delivery fees are waived on orders placed during your paid month, across stores in {campus}. Normal delivery areas and ordering windows still apply.', { campus: data?.campus_name || msg('FE_PASS_YOUR_CAMPUS', 'your campus') })}</DialogDescription></div>
      {error && <div role="alert" className="space-y-2 rounded-xl border border-destructive/30 p-3 text-sm"><p>{error}</p><button disabled={busy} className="font-bold underline" onClick={reloadSafe}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>}
      {proof?.status === 'credited' && <p role="status" className="rounded-xl bg-success/10 p-3 text-sm font-bold text-success">{msg('FE_PASS_RECOVERED', 'Payment recovered to your app wallet')}</p>}
      {active ? <div className="space-y-4"><div className="rounded-2xl border border-success/20 bg-success/5 p-4"><span className="inline-flex items-center gap-1.5 text-xs font-bold text-success"><ShieldCheck className="h-4 w-4" />{msg('FE_PASS_PAID', 'Your delivery pass is active')}</span><p className="mt-2 font-heading text-lg font-extrabold">{passDate(until)}</p><p className="mt-1 text-xs text-muted-foreground">{formatNaira((membership?.price_kobo || proof?.amount_kobo || 0) / 100)} {msg('FE_PASS_MONTH', 'per month')}</p></div>
        {membership?.auto_renew ? <button disabled={busy} className={`${secondary} w-full`} onClick={() => run(() => apiClient.post('/delivery-pass/renewal', { enabled: false }))}>{msg('FE_PASS_STOP_RENEWAL', 'Stop automatic renewal')}</button> : <><label className="flex items-start gap-3 text-xs leading-relaxed"><input className="mt-0.5" type="checkbox" disabled={busy || !data?.renewals_ready} checked={renew} onChange={event => setRenew(event.target.checked)} />{msg('FE_PASS_RENEW_TERMS', 'Automatically renew from my wallet for {amount} each month until I stop renewal. This does not authorise a bank or card debit.', { amount: formatNaira(price) })}</label>{data?.renewals_ready && <button disabled={busy || !renew} className={primary} onClick={() => run(() => apiClient.post('/delivery-pass/renewal', { enabled: true, price, consent_version: data.consent_version }))}>{msg('FE_PASS_ENABLE_RENEWAL', 'Enable wallet renewal')}</button>}</>}
        {!data?.renewals_ready && <p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_PASS_RENEW_PAUSED', 'Automatic renewal is currently unavailable. You can renew manually when your month ends.')}</p>}
      </div> : pending ? <div className="space-y-3"><div className="rounded-2xl bg-secondary/60 p-4"><p className="font-bold">{msg('FE_PASS_PENDING', 'Payment awaiting confirmation')}</p><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{pendingExpired ? msg('FE_PASS_EXPIRED_PAYMENT', 'This purchase window has ended. Check the original payment or cancel it before buying another pass.') : msg('FE_PASS_PENDING_HELP', 'Your pass starts after payment is verified. Check this payment before starting another.')}</p><p className="mt-3 font-heading text-2xl font-extrabold">{formatNaira(pending.amount_kobo / 100)}</p></div>
        {!pendingExpired && pending.checkout_url?.startsWith('https://checkout.paystack.com/') && <button disabled={busy} className={primary} onClick={() => window.location.assign(pending.checkout_url)}>{msg('FE_PASS_CONTINUE_PAYMENT', 'Continue payment')}<ArrowUpRight className="h-4 w-4" /></button>}
        <button disabled={busy} className={`${secondary} flex w-full items-center justify-center gap-2`} onClick={() => verify(pending.id)}><RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />{msg('FE_PASS_CHECK_PAYMENT', 'Check payment')}</button><button disabled={busy} className="min-h-11 w-full text-xs font-bold text-muted-foreground underline" onClick={() => run(() => apiClient.post(`/delivery-pass/receipts/${pending.id}/cancel`, {}), { cancelled: true })}>{msg('FE_PASS_CANCEL_PAYMENT', 'Cancel pending purchase')}</button><p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_PASS_CANCEL_WARNING', 'A payment that succeeds after cancellation is returned to your app wallet.')}</p>
      </div> : data?.available ? <form className="space-y-4" onSubmit={event => { event.preventDefault(); void run(() => apiClient.post('/delivery-pass/buy', intent.body({ method, price, auto_renew: renew, consent_version: renew ? data.consent_version : undefined }))); }}>
        <div className="flex items-end gap-2 border-y border-border py-4"><strong className="font-heading text-4xl font-extrabold tracking-tight">{formatNaira(price)}</strong><span className="pb-1 text-xs text-muted-foreground">{msg('FE_PASS_MONTH', 'per month')}</span></div>
        <fieldset disabled={busy || !!error}><legend className="text-xs font-bold">{msg('FE_PASS_PAY_WITH', 'Pay with')}</legend><div className="mt-2 grid grid-cols-2 gap-3">{methods.map(({ value, Icon, key, fallback }) => <label key={value as string} className={`relative flex cursor-pointer items-center gap-2 rounded-2xl border p-3 text-sm font-bold ${method === value ? 'border-primary bg-primary/5' : 'border-border'} ${value === 'card' && !data.card_available ? 'opacity-40' : ''}`}><input type="radio" name="delivery-pass-method" value={value as string} checked={method === value} disabled={value === 'card' && !data.card_available} onChange={() => setMethod(value as string)} className="sr-only peer" /><span className="absolute inset-0 rounded-2xl peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2" /><Icon className="h-4 w-4" />{msg(key as string, fallback as string)}{method === value && <Check className="ml-auto h-4 w-4 text-primary" />}</label>)}</div></fieldset>
        <label className="flex items-start gap-3 text-xs leading-relaxed"><input className="mt-0.5" type="checkbox" disabled={busy || !data.renewals_ready} checked={renew} onChange={event => setRenew(event.target.checked)} />{msg('FE_PASS_RENEW_TERMS', 'Automatically renew from my wallet for {amount} each month until I stop renewal. This does not authorise a bank or card debit.', { amount: formatNaira(price) })}</label>
        {!data.renewals_ready && <p className="text-xs text-muted-foreground">{msg('FE_PASS_RENEW_PAUSED', 'Automatic renewal is currently unavailable. You can renew manually when your month ends.')}</p>}
        {method === 'card' && <p className="text-xs text-muted-foreground">{msg('FE_PASS_GATEWAY_FEE', 'Card checkout may add the payment provider’s processing fee. Wallet payments use the price shown.')}</p>}
        <button type="submit" disabled={busy || !!error || price <= 0 || method === 'card' && !data.card_available} className={primary}>{busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}{msg('FE_PASS_BUY', 'Pay {amount} for one month', { amount: formatNaira(price) })}</button>
      </form> : !error && <p className="text-sm text-muted-foreground">{msg('PASS_UNAVAILABLE', 'Delivery passes are not available for this campus right now.')}</p>}
      {!!data?.history?.length && <details className="border-t border-border pt-4"><summary className="cursor-pointer text-sm font-bold">{msg('FE_PASS_HISTORY', 'Pass payments')}</summary><div className="mt-3 space-y-3">{data.history.map(row => <div key={row.id} className="flex justify-between gap-3 text-xs"><div><p className="font-bold">{formatNaira(row.amount_kobo / 100)}</p><time className="text-muted-foreground" dateTime={row.created_at}>{passDate(row.created_at)}</time></div><span className="text-right font-semibold">{passStatus(row.status)}</span></div>)}</div></details>}
    </DialogContent></Dialog>
  </>;
}
