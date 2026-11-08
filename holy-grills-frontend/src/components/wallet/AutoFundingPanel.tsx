import { useCallback, useEffect, useRef, useState } from 'react';
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
  const inputClass = 'w-full mt-1 rounded-xl border border-border bg-background p-3 min-w-0';

  return <div className="space-y-4" aria-busy={busy || loading}>
    <p className="text-sm text-muted-foreground">Choose your amount and frequency. Paystack securely authorizes your card with your first contribution now. Every successful contribution is available to spend immediately. Holy Grills covers processing fees.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {notice && <p role="status" className="text-sm text-foreground">{notice}</p>}
    {(error || isReturn) && <button type="button" disabled={busy} className="text-sm font-bold text-primary disabled:opacity-50" onClick={async () => {
      if (isReturn) await checkPayment();
      else { setLoading(true); try { await load(); setError(''); } catch { setError('Funding unavailable. Please try again.'); } finally { setLoading(false); } }
    }}>{isReturn ? 'Check payment and refresh' : 'Refresh funding'}</button>}
    {loading && <p role="status" className="text-sm">Loading your funding plans…</p>}
    {!loading && plans.map(plan => <div key={plan.id} className="rounded-xl border border-border p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2"><strong>{formatNaira(plan.amount_kobo / 100)} every {plan.interval_days} {plan.interval_days === 1 ? 'day' : 'days'}</strong><span className="text-xs font-bold">{stateLabels[plan.state]}</span></div>
      <p className="text-sm text-muted-foreground">{plan.successful_payments} successful {plan.successful_payments === 1 ? 'contribution' : 'contributions'} · {formatNaira(plan.total_credited_kobo / 100)} funded{plan.card_label ? ` · ${plan.card_label}` : ''}</p>
      <p className="text-xs text-muted-foreground">{plan.stop_after ? `Stops after ${plan.stop_after} contributions, including your first payment.` : plan.end_at ? `Stops before ${showDate(plan.end_at)} (WAT).` : 'Continues until you stop it.'}</p>
      {plan.next_due_at && <p className="text-sm">Next contribution: {showDate(plan.next_due_at)} WAT</p>}
      {plan.state === 'attention' && <p className="text-sm">Automatic payments are paused. Your funded balance is safe. Stop this plan and set up a new one to authorize your card again.</p>}
      {plan.in_flight && <p role="status" className="text-sm">A payment is being checked. We will confirm its result before charging again.</p>}
      {plan.state === 'draft' && plan.checkout_url && <button type="button" disabled={busy} onClick={() => followCheckout(plan.checkout_url)} className="font-bold text-primary text-sm">Continue first payment</button>}
      {['draft', 'active', 'attention'].includes(plan.state) && <div>
        {confirmStop === plan.id ? <div className="space-y-2"><p className="text-sm">Stop future contributions? Payments already processing may still finish. An open first-payment link may still accept payment; please close it.</p><div className="flex gap-4"><button type="button" disabled={busy} onClick={() => stop(plan.id)} className="font-bold text-destructive text-sm">Yes, stop funding</button><button type="button" disabled={busy} onClick={() => setConfirmStop(null)} className="text-sm">Keep plan</button></div></div>
          : <button type="button" disabled={busy} onClick={() => setConfirmStop(plan.id)} className="font-bold text-destructive text-sm">Stop automatic funding</button>}
      </div>}
    </div>)}
    {limits?.enabled === false && <p role="status" className="text-sm">Holy Grills has paused new automatic contributions. Existing payments are still being checked, and your wallet remains available.</p>}
    {!loading && limits && limits.enabled !== false && !openPlan && <form onSubmit={create} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="text-sm font-bold">Amount per contribution (₦)<input className={inputClass} type="number" min={limits.minimum_amount} max={limits.maximum_amount} step="0.01" inputMode="decimal" required value={amount} onChange={e => { setAmount(e.target.value); setConsent(false); }} /></label>
        <label className="text-sm font-bold">Contribute every (days)<input className={inputClass} type="number" min="1" max={limits.maximum_interval_days} step="1" inputMode="numeric" required value={days} onChange={e => { setDays(e.target.value); setConsent(false); }} /></label>
      </div>
      <label className="block text-sm font-bold">Automatic stop<select className={inputClass} value={stopMode} onChange={e => { setStopMode(e.target.value); setConsent(false); }}><option value="count">After a number of contributions</option><option value="date">On a date</option><option value="none">When I stop it</option></select></label>
      {stopMode === 'count' && <label className="block text-sm font-bold">Total contributions, including today<input className={inputClass} type="number" min="1" max="3650" step="1" required value={count} onChange={e => { setCount(e.target.value); setConsent(false); }} /></label>}
      {stopMode === 'date' && <label className="block text-sm font-bold">Last day to contribute (Nigeria time)<input className={inputClass} type="date" required value={endDate} onChange={e => { setEndDate(e.target.value); setConsent(false); }} /></label>}
      <p className="text-xs text-muted-foreground">Payments run approximately at your setup time, every {days || 'chosen number of'} days. Missed processing windows are never charged in a burst. A failed or uncertain payment pauses further charges until resolved. Stop any time; money already funded stays in your wallet.</p>
      <label className="flex gap-3 text-sm items-start"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-1 accent-primary" /><span>I authorize {formatNaira(Number(amount) || 0)} now and every {days || 'chosen number of'} days{stopMode === 'count' ? `, up to ${count || 'the selected number of'} contributions including today` : stopMode === 'date' ? `, through ${endDate || 'my chosen end date'}` : ', until I stop this plan'}. I can stop future contributions at any time. Holy Grills pays the processing fee.</span></label>
      <button type="submit" disabled={busy || !consent} className="w-full rounded-xl bg-gradient-cta text-white p-3 font-bold disabled:opacity-50">{busy ? 'Setting up…' : `Authorize and fund ${formatNaira(Number(amount) || 0)}`}</button>
    </form>}
  </div>;
}
