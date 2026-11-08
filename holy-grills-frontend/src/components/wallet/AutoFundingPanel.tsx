import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, ChevronDown, Clock3, CreditCard, Loader2, Repeat2, ShieldCheck, Wallet } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { isAllowedPaymentUrl } from '@/lib/safeNavigation';
import type { AutoFundingPlan, AutoFundingLimits } from '@/types/wallet';

const stateLabels = { draft: 'Awaiting first payment', active: 'Active', attention: 'Needs attention', stopped: 'Stopped', completed: 'Completed' };
const showDate = (value: string) => new Intl.DateTimeFormat('en-NG', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(new Date(value));

interface Props {
  reference?: string | null;
  planId?: string | null;
  onPaid: () => void | Promise<void>;
}

export default function AutoFundingPanel({ reference, planId, onPaid }: Props) {
  const [plans, setPlans] = useState<AutoFundingPlan[]>([]);
  const [limits, setLimits] = useState<AutoFundingLimits | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [amount, setAmount] = useState('200');
  const [days, setDays] = useState('2');
  const [customFrequency, setCustomFrequency] = useState(false);
  const [stopMode, setStopMode] = useState('count');
  const [count, setCount] = useState('30');
  const [endDate, setEndDate] = useState('');
  const [consent, setConsent] = useState(false);
  const [confirmStop, setConfirmStop] = useState<string | null>(null);
  const intent = useRef<{ terms: string; id: string } | null>(null);
  const handledReturn = useRef(false);
  const readGeneration = useRef(0);
  const onPaidRef = useRef(onPaid);
  onPaidRef.current = onPaid;

  const load = useCallback(async () => {
    const generation = ++readGeneration.current;
    const result = await liveApi.wallet.getAutoFunding();
    if (generation !== readGeneration.current) return;
    setPlans(result.plans);
    setLimits(result.limits);
  }, []);

  useEffect(() => {
    let current = true;
    const generation = ++readGeneration.current;
    // This component mounts only after opening the card. No Dashboard request
    // and no extra blocking work for ordinary Wallet visitors.
    liveApi.wallet.getAutoFunding().then(result => {
      if (current && generation === readGeneration.current) { setPlans(result.plans); setLimits(result.limits); }
    }).catch(() => { if (current && generation === readGeneration.current) setError('Automatic funding could not be loaded. Please refresh.'); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, []);

  const checkPayment = useCallback(async () => {
    if (!reference || !planId || planId === '1') return;
    setBusy(true); setError('');
    try {
      const result = await liveApi.wallet.verifyAutoFunding(planId, { reference });
      if (result.payment_status === 'paid') {
        setNotice('Payment received. Your wallet is ready to use. Check the plan status below.');
        await onPaidRef.current();
      } else setNotice('Payment is not confirmed yet. Check again before starting another payment.');
      await load();
    } catch { setError('Payment could not be confirmed. Check again; do not start another payment.'); }
    finally { setBusy(false); }
  }, [reference, planId, load]);

  useEffect(() => {
    if (reference && planId && planId !== '1' && !handledReturn.current) {
      handledReturn.current = true;
      void checkPayment();
    }
  }, [reference, planId, checkPayment]);

  const followCheckout = (url?: string | null) => {
    if (!url || !isAllowedPaymentUrl(url)) {
      setError('The payment link is unavailable. Refresh this plan before trying again.');
      return;
    }
    window.location.assign(url);
  };

  const create = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !consent || !limits) return;
    setBusy(true); setError(''); setNotice('');
    const terms = { amount: Number(amount), interval_days: Number(days),
      stop_after: stopMode === 'count' ? Number(count) : null,
      end_date: stopMode === 'date' ? endDate : null,
      consent: true, consent_version: limits.consent_version };
    const serialized = JSON.stringify(terms);
    if (!intent.current || intent.current.terms !== serialized) intent.current = { terms: serialized, id: crypto.randomUUID() };
    try {
      const result = await liveApi.wallet.createAutoFunding({ ...terms, request_id: intent.current.id });
      await load();
      followCheckout(result.plan.checkout_url);
    } catch (err) {
      setError(err?.message || 'Funding setup could not be confirmed. Refresh before trying again.');
      try { await load(); } catch { /* retain the original error */ }
    } finally { setBusy(false); }
  };

  const stop = async (id: string) => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await liveApi.wallet.stopAutoFunding(id);
      setNotice(result.plan.in_flight
        ? 'Future payments stopped. A payment already processing may still complete and will be credited to your wallet.'
        : 'Automatic funding stopped. Your wallet balance stays available.');
      setConfirmStop(null); setConsent(false); intent.current = null;
      await load();
    } catch { setError('Stopping could not be confirmed. Refresh the plan and check its status.'); }
    finally { setBusy(false); }
  };

  const openPlan = plans.find(p => ['draft', 'active', 'attention'].includes(p.state));
  const isReturn = Boolean(reference && planId && planId !== '1');
  const inputClass = 'w-full min-w-0 rounded-xl border border-border bg-background px-3 py-2.5 text-base font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:opacity-60';
  const frequencyLabel = days === '1' ? 'Daily' : days === '7' ? 'Weekly' : `Every ${days || '…'} days`;
  const numericAmount = Number(amount);
  const numericCount = Number(count);
  const summaryAmount = Number.isFinite(numericAmount) && numericAmount > 0 ? formatNaira(numericAmount) : '—';
  const plannedTotal = Number.isFinite(numericAmount * numericCount) && numericAmount > 0 && Number.isInteger(numericCount) && numericCount > 0
    ? formatNaira(numericAmount * numericCount) : '—';
  const parsedEndDate = endDate ? new Date(`${endDate}T00:00:00+01:00`) : null;
  const dateLabel = parsedEndDate && Number.isFinite(parsedEndDate.getTime())
    ? new Intl.DateTimeFormat('en-NG', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Lagos' }).format(parsedEndDate) : 'Choose a date';

  return <div className="space-y-5" aria-busy={busy || loading}>
    <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs font-semibold text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-success" aria-hidden="true" />No extra fees</span>
      <span className="inline-flex items-center gap-1.5"><Wallet className="h-3.5 w-3.5 text-primary" aria-hidden="true" />Always available to spend</span>
    </div>
    {error && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="rounded-xl border border-success/20 bg-success/5 p-3 text-sm text-foreground">{notice}</p>}
    {(error || isReturn) && <button type="button" disabled={busy} className="text-sm font-bold text-primary disabled:opacity-50" onClick={async () => {
      if (isReturn) await checkPayment();
      else { setLoading(true); try { await load(); setError(''); } catch { setError('Funding unavailable. Please try again.'); } finally { setLoading(false); } }
    }}>{isReturn ? 'Check payment and refresh' : 'Refresh funding'}</button>}
    {loading && <p role="status" className="flex items-center gap-2 py-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />Loading your funding plans…</p>}
    {!loading && plans.map(plan => <div key={plan.id} className="overflow-hidden rounded-2xl border border-border">
      <div className="flex items-start justify-between gap-3 bg-background/70 p-4">
        <div className="min-w-0"><p className="font-heading text-2xl font-extrabold break-words">{formatNaira(plan.amount_kobo / 100)}</p><p className="mt-0.5 text-xs text-muted-foreground">Every {plan.interval_days} {plan.interval_days === 1 ? 'day' : 'days'}</p></div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${plan.state === 'active' ? 'bg-success/10 text-success' : plan.state === 'attention' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}>{stateLabels[plan.state]}</span>
      </div>
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-3"><div><p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Contributions</p><p className="mt-1 text-sm font-bold">{plan.successful_payments}{plan.stop_after ? ` / ${plan.stop_after}` : ''}</p></div><div><p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Wallet funded</p><p className="mt-1 text-sm font-bold break-words">{formatNaira(plan.total_credited_kobo / 100)}</p></div></div>
        {plan.stop_after && <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true"><div className="h-full rounded-full bg-success" style={{ width: `${Math.min(100, Math.max(0, plan.successful_payments / plan.stop_after * 100))}%` }} /></div>}
        {plan.card_label && <p className="flex items-center gap-2 text-xs text-muted-foreground"><CreditCard className="h-3.5 w-3.5" aria-hidden="true" />{plan.card_label}</p>}
        <p className="text-xs text-muted-foreground">{plan.stop_after ? `Stops after ${plan.stop_after} contributions, including your first payment.` : plan.end_at ? `Stops before ${showDate(plan.end_at)} (WAT).` : 'Continues until you stop it.'}</p>
        {plan.next_due_at && <p className="flex items-start gap-2 rounded-xl bg-background p-3 text-xs"><Clock3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" /><span>Next contribution<br /><strong>{showDate(plan.next_due_at)} WAT</strong></span></p>}
        {plan.state === 'attention' && <p className="rounded-xl bg-primary/5 p-3 text-sm">Automatic payments are paused. Your funded balance is safe. Stop this plan and set up a new one to authorize your card again.</p>}
        {plan.in_flight && <p role="status" className="text-sm text-muted-foreground">A payment is being checked. We will confirm its result before charging again.</p>}
        {plan.state === 'draft' && plan.checkout_url && <button type="button" disabled={busy} onClick={() => followCheckout(plan.checkout_url)} className="w-full rounded-xl bg-gradient-cta p-3 font-bold text-white disabled:opacity-50">Continue first payment</button>}
        {['draft', 'active', 'attention'].includes(plan.state) && <div className="border-t border-border pt-3">
          {confirmStop === plan.id ? <div className="space-y-3"><p className="text-sm">Stop future contributions? Payments already processing may still finish. An open first-payment link may still accept payment; please close it.</p><div className="flex flex-wrap gap-3"><button type="button" disabled={busy} onClick={() => stop(plan.id)} className="rounded-lg bg-destructive/10 px-3 py-2 font-bold text-destructive text-sm">Yes, stop funding</button><button type="button" disabled={busy} onClick={() => setConfirmStop(null)} className="px-3 py-2 text-sm font-semibold">Keep plan</button></div></div>
            : <button type="button" disabled={busy} onClick={() => setConfirmStop(plan.id)} className="py-1 font-bold text-destructive text-xs">Stop automatic funding</button>}
        </div>}
      </div>
    </div>)}
    {limits?.enabled === false && <p role="status" className="text-sm">Holy Grills has paused new automatic contributions. Existing payments are still being checked, and your wallet remains available.</p>}
    {!loading && limits && limits.enabled !== false && !openPlan && <form onSubmit={create} className="space-y-4">
      <fieldset disabled={busy} className="min-w-0 space-y-3">
        <legend className="flex items-center gap-2 text-sm font-bold"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] text-primary" aria-hidden="true">1</span>Choose your amount</legend>
        <label htmlFor="auto-funding-amount" className="sr-only">Amount per contribution (₦)</label>
        <div className="flex items-center gap-2 rounded-2xl border border-border bg-background px-4 py-3 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15"><span className="text-xl font-semibold text-muted-foreground" aria-hidden="true">₦</span><input id="auto-funding-amount" className="w-full min-w-0 bg-transparent text-3xl font-extrabold tabular-nums outline-none" type="number" min={limits.minimum_amount} max={limits.maximum_amount} step="0.01" inputMode="decimal" required value={amount} onChange={e => { setAmount(e.target.value); setConsent(false); }} /></div>
        <div className="flex flex-wrap gap-2">{[200, 500, 1000, 2000].filter(value => value >= limits.minimum_amount && value <= limits.maximum_amount).map(value => <button key={value} type="button" aria-pressed={Number(amount) === value} onClick={() => { setAmount(String(value)); setConsent(false); }} className={`rounded-full border px-3 py-2 text-xs font-bold transition-colors ${Number(amount) === value ? 'border-primary bg-primary/5 text-primary' : 'border-border hover:border-primary/40'}`}>{formatNaira(value)}</button>)}</div>
      </fieldset>

      <fieldset disabled={busy} className="min-w-0 space-y-3">
        <legend className="flex items-center gap-2 text-sm font-bold"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] text-primary" aria-hidden="true">2</span>Make it a rhythm</legend>
        <div className="grid grid-cols-4 gap-2">{[{ value: '1', label: 'Daily' }, { value: '2', label: 'Every 2 days', shortLabel: '2 days' }, { value: '7', label: 'Weekly' }, { value: 'custom', label: 'Custom' }].map(option => {
          const selected = option.value === 'custom' ? customFrequency : !customFrequency && days === option.value;
          return <button key={option.value} type="button" aria-label={option.label} aria-pressed={selected} onClick={() => { setCustomFrequency(option.value === 'custom'); if (option.value !== 'custom') setDays(option.value); setConsent(false); }} className={`flex min-h-11 items-center justify-center gap-1.5 rounded-xl border px-2 py-2.5 text-xs font-bold transition-colors ${selected ? 'border-primary bg-primary/5 text-primary' : 'border-border hover:border-primary/40'}`}>{selected && <Check className="hidden h-3 w-3 shrink-0 sm:block" aria-hidden="true" />}{option.shortLabel || option.label}</button>;
        })}</div>
        {customFrequency && <label className="block text-xs font-semibold text-muted-foreground">Contribute every (days)<input className={`${inputClass} mt-1.5`} type="number" min="1" max={limits.maximum_interval_days} step="1" inputMode="numeric" required value={days} onChange={e => { setDays(e.target.value); setConsent(false); }} /></label>}
      </fieldset>

      <fieldset disabled={busy} className="min-w-0 space-y-3">
        <legend className="flex items-center gap-2 text-sm font-bold"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] text-primary" aria-hidden="true">3</span>Choose when to stop</legend>
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-background p-1">{[{ value: 'count', label: 'After payments' }, { value: 'date', label: 'On a date' }, { value: 'none', label: 'I’ll stop it' }].map(option => <button key={option.value} type="button" aria-pressed={stopMode === option.value} onClick={() => { setStopMode(option.value); setConsent(false); }} className={`min-h-11 rounded-lg px-1.5 py-2 text-[11px] font-bold transition-colors ${stopMode === option.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>{option.label}</button>)}</div>
        {stopMode === 'count' && <div className="flex items-center justify-between gap-3 rounded-xl border border-border px-3 py-2.5"><label htmlFor="auto-funding-count" className="min-w-0"><span className="block text-xs font-bold">Number of payments</span><span className="mt-0.5 block text-[11px] text-muted-foreground">Includes your first payment today</span></label><input id="auto-funding-count" aria-label="Total contributions, including today" className="w-20 shrink-0 rounded-lg border border-border bg-background p-2 text-center text-base font-bold outline-none focus:border-primary focus:ring-2 focus:ring-primary/15" type="number" min="1" max="3650" step="1" required value={count} onChange={e => { setCount(e.target.value); setConsent(false); }} /></div>}
        {stopMode === 'date' && <label className="block text-xs font-semibold text-muted-foreground">Last day to contribute (Nigeria time)<input className={`${inputClass} mt-1.5`} type="date" required value={endDate} onChange={e => { setEndDate(e.target.value); setConsent(false); }} /></label>}
      </fieldset>

      <section className="relative overflow-hidden rounded-2xl bg-brand-brown p-4 text-white" aria-label="Funding plan summary">
        <Repeat2 className="pointer-events-none absolute -right-3 -top-3 h-24 w-24 -rotate-12 text-white/5" aria-hidden="true" />
        <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">Your plan</p>
        <div className="relative mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1"><strong className="font-heading text-2xl font-extrabold break-words">{summaryAmount}</strong><span className="text-xs text-white/75">{frequencyLabel.toLowerCase()}</span></div>
        <div className="relative mt-3 grid grid-cols-2 gap-3 border-t border-white/15 pt-3 text-xs"><div><p className="text-white/60">First payment</p><p className="mt-1 font-bold">Today</p></div><div><p className="text-white/60">{stopMode === 'count' ? 'Planned total' : stopMode === 'date' ? 'End date' : 'Ends'}</p><p className="mt-1 font-bold break-words">{stopMode === 'count' ? plannedTotal : stopMode === 'date' ? dateLabel : 'When you stop it'}</p></div></div>
        <p className="relative mt-3 text-[11px] text-white/75">Holy Grills covers all Paystack fees.</p>
      </section>

      <details className="group rounded-xl border border-border px-3 py-2.5 text-xs text-muted-foreground"><summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-semibold">How payments work<ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" aria-hidden="true" /></summary><p className="pt-2 leading-relaxed">Paystack authorizes your card with your first payment today. Later payments run approximately at your setup time, every {days || 'chosen number of'} days. Missed windows are never charged in a burst. A failed or uncertain payment pauses further charges until resolved. Stopping does not remove money already in your wallet.</p></details>
      <label className="flex items-start gap-3 rounded-xl bg-background p-3 text-xs leading-relaxed"><input type="checkbox" required disabled={busy} checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-primary" /><span>I authorize {summaryAmount} today and every {days || 'chosen number of'} days{stopMode === 'count' ? `, for up to ${count || 'the selected number of'} payments including today` : stopMode === 'date' ? `, through ${endDate || 'my chosen end date'}` : ', until I stop this plan'}. I can stop future payments at any time.</span></label>
      <button type="submit" disabled={busy || !consent} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-cta px-3 py-3.5 text-sm font-bold text-white transition-opacity disabled:opacity-50">{busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />Setting up…</> : <>Authorize and fund {summaryAmount}<ArrowRight className="h-4 w-4" aria-hidden="true" /></>}</button>
      <p className="flex items-center justify-center gap-1.5 text-[10px] text-muted-foreground"><ShieldCheck className="h-3 w-3" aria-hidden="true" />Card payments secured by Paystack</p>
    </form>}
  </div>;
}
