import { useEffect, useRef, useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Check, ChevronRight, RefreshCw, Repeat2, Truck, Users } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira } from '@/lib/hgUtils';
import { passDate, passStatus } from '@/lib/deliveryPass';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const primary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-primary px-5 text-sm font-bold text-primary-foreground disabled:opacity-50';
const secondary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-border px-4 text-sm font-semibold disabled:opacity-50';
const control = 'mt-2 min-h-12 w-full rounded-xl border border-border bg-background px-3 text-base';
const money = (value: number) => formatNaira(Number(value || 0) / 100);
export default function AdminDeliveryPass() {
  const { user } = useHolyGrill();
  const { adminCampusId, campusId } = useCampus();
  const selected = user?.role === 'super_admin' ? adminCampusId : campusId;
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [price, setPrice] = useState('');
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<any>(null);
  const [reason, setReason] = useState('');
  const [ack, setAck] = useState(false);
  const [actionError, setActionError] = useState('');
  const locked = useRef(false);
  const version = useRef(0);
  const load = async () => {
    const key = ++version.current; setLoading(true); setError(''); setResult(null);
    try {
      const value = await apiClient.get('/admin/delivery-pass', selected ? { campus_id: selected } : {});
      if (key !== version.current) return;
      setResult(value); setPrice(value.offer ? String(value.offer.price_kobo / 100) : ''); setActive(!!value.offer?.is_active);
    } catch (failure) { if (key === version.current) setError(failure.message); }
    finally { if (key === version.current) setLoading(false); }
  };
  useEffect(() => { setReceipt(null); setActionError(''); load(); return () => { version.current++; }; }, [selected, user?.id]);
  const act = async (operation: () => Promise<unknown>, title: string) => {
    if (locked.current) return;
    locked.current = true; setBusy(true); setActionError(''); const key = version.current;
    try {
      await operation();
      if (key === version.current) { setReceipt(null); toast({ title }); await load(); }
    } catch (failure) { if (key === version.current) setActionError(failure.message); }
    finally { locked.current = false; setBusy(false); }
  };
  const save = event => {
    event.preventDefault();
    return act(() => apiClient.patch('/admin/delivery-pass', { campus_id: selected, price: Number(price), is_active: active, expected_updated_at: result.offer?.updated_at ?? null }), msg('FE_PASS_CONFIG_SAVED', 'Delivery plan saved'));
  };
  const stats = [
    { label: msg('FE_PASS_ACTIVE_MEMBERS', 'Active passes'), value: result?.active_members ?? 0, Icon: Users },
    { label: msg('FE_PASS_RENEWING_MEMBERS', 'Wallet renewals'), value: result?.renewing_members ?? 0, Icon: Repeat2 },
    { label: msg('FE_PASS_SALES', 'Sales after refunds'), value: money(result?.revenue_kobo), Icon: ArrowUpRight },
    { label: msg('FE_PASS_REFUNDS', 'Refunds to wallet'), value: money(result?.refunds_kobo), Icon: ArrowDownLeft },
  ];
  return <div className="mx-auto max-w-6xl space-y-7 pb-10">
    <header className="flex items-start justify-between gap-4"><div><div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-primary"><Truck className="h-4 w-4"/>{msg('FE_PASS_TITLE', 'Delivery pass')}</div><h2 className="font-heading text-2xl font-extrabold sm:text-3xl">{msg('FE_PASS_CONFIG_TITLE', 'Delivery subscriptions')}</h2><p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">{msg('FE_PASS_CONFIG_HELP', 'One campus plan, honoured across all its stores. New prices apply to new purchases; existing wallet renewals keep their agreed price.')}</p></div><button type="button" className={secondary + ' shrink-0 px-3'} disabled={loading || busy} onClick={load} aria-label={msg('FE_PLATFORM_RETRY', 'Retry')}><RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')}/></button></header>
    {loading ? <div className="space-y-4 animate-pulse" role="status" aria-label={msg('FE_PASS_LOADING', 'Loading delivery subscriptions…')}><div className="h-24 rounded-2xl bg-secondary"/><div className="h-64 rounded-2xl bg-secondary"/></div> : error ? <div role="alert" className="space-y-4 rounded-2xl border border-destructive/20 p-5"><p>{error}</p><button type="button" className={primary} onClick={load}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div> : result && <>
      <div className="grid grid-cols-2 gap-x-5 gap-y-6 border-y border-border py-5 lg:grid-cols-4">{stats.map(({label,value,Icon}) => <div key={label} className="min-w-0"><p className="mb-3 flex items-center gap-2 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5 shrink-0"/>{label}</p><p className="break-words font-heading text-2xl font-extrabold tracking-tight">{value}</p></div>)}</div>
      <div className="grid items-start gap-7 lg:grid-cols-[minmax(250px,0.8fr)_minmax(0,1.5fr)]">
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-6"><h3 className="font-heading text-lg font-bold">{msg('FE_PASS_SUBTITLE', 'One month. Delivery covered.')}</h3>{selected ? <form onSubmit={save} className="mt-5 space-y-5"><label className="block text-sm font-semibold">{msg('FE_PASS_PRICE', 'Monthly price (₦)')}<input type="number" min="100" max="1000000" step="0.01" required value={price} disabled={busy} onChange={e => setPrice(e.target.value)} className={control}/></label><label className="flex items-start gap-3 text-sm leading-relaxed"><input type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={active} disabled={busy} onChange={e=>setActive(e.target.checked)}/>{msg('FE_PASS_OFFER_ACTIVE', 'Offer this plan to new customers')}</label>{!result.enabled && <p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_PASS_FLAG_OFF', 'Purchases are paused. Save an active plan and enable the delivery-pass feature flag when ready. Already-paid coverage remains valid.')}</p>}<button className={primary + ' w-full'} disabled={busy}><Check className="h-4 w-4"/>{msg('FE_PASS_CONFIG_SAVE', 'Save delivery plan')}</button></form> : <p className="mt-4 text-sm text-muted-foreground">{msg('FE_PASS_SELECT_CAMPUS', 'Select a campus in the header to configure its plan. This overview includes all campuses.')}</p>}{!result.renewals_ready && <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">{msg('FE_PASS_WORKER_OFF', 'Automatic renewal has no recent worker heartbeat. Customers can buy a month, but cannot enable automatic renewal until the hourly job is running.')}</p>}</section>
        <section className="min-w-0"><div className="mb-4 flex items-center justify-between gap-3"><h3 className="font-heading text-lg font-bold">{msg('FE_PASS_HISTORY', 'Pass payments')}</h3><span className="text-xs text-muted-foreground">{msg('FE_PASS_LATEST', 'Latest 50')}</span></div><p className="mb-4 text-xs leading-relaxed text-muted-foreground">{msg('FE_PASS_REPORT_BASIS', 'Membership counts are current. Pass sales and refunds are all time; recovered payments are wallet funds, not pass sales.')}</p><div className="divide-y divide-border">{(result.receipts || []).map(row=><div key={row.id} className="flex items-start justify-between gap-4 py-4"><div className="min-w-0"><p className="truncate text-sm font-bold">{row.full_name}</p><p className="mt-1 text-xs text-muted-foreground">{passDate(row.created_at)}</p><p className="mt-2 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-secondary px-2.5 py-1">{passStatus(row.status)}</span>{row.is_test && <span className="rounded-full bg-secondary px-2.5 py-1">{msg('FE_PASS_TEST', 'Test payment')}</span>}</p></div><div className="shrink-0 text-right"><p className="font-bold">{money(row.amount_kobo)}</p>{row.status==='paid' && <button type="button" className="mt-2 inline-flex min-h-10 items-center gap-1 text-xs font-bold text-primary" disabled={busy} onClick={()=>{setReceipt(row);setReason('');setAck(false);setActionError('');}}>{msg('FE_PASS_REFUND_ACTION', 'Refund pass')}<ChevronRight className="h-3 w-3"/></button>}</div></div>)}</div>{!result.receipts?.length && <p className="border-y border-dashed border-border py-10 text-center text-sm text-muted-foreground">{msg('FE_PASS_NO_RECEIPTS', 'No delivery-pass payments in this scope yet.')}</p>}</section>
      </div>
    </>}
    {actionError && !receipt && <p role="alert" className="text-sm text-destructive">{actionError}</p>}
    <Dialog open={!!receipt} onOpenChange={open=>{if(!open && !busy)setReceipt(null);}}><DialogContent className="max-h-[90dvh] overflow-y-auto rounded-3xl sm:max-w-md"><DialogHeader className="text-left"><DialogTitle>{msg('FE_PASS_REFUND_ACTION', 'Refund pass')}</DialogTitle><DialogDescription>{msg('FE_PASS_REFUND_HELP', 'Return the full pass price to the app wallet. Refunding the current period ends future coverage and stops renewal; existing orders keep their agreed prices.')}</DialogDescription></DialogHeader><form className="space-y-5" onSubmit={event=>{event.preventDefault();act(()=>apiClient.post(`/admin/delivery-pass/receipts/${receipt.id}/refund`, {reason,acknowledge:ack}),msg('FE_PASS_REFUNDED','Pass refunded to the app wallet'));}}><div className="border-y border-border py-4"><p className="text-sm">{receipt?.full_name}</p><p className="mt-1 font-heading text-2xl font-bold">{money(receipt?.amount_kobo)}</p></div><label className="block text-sm font-semibold">{msg('FE_PASS_REFUND_REASON', 'Reason for refund')}<textarea required maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)} className={control + ' min-h-24 py-3'} disabled={busy}/></label><label className="flex items-start gap-3 text-sm leading-relaxed"><input required type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)} disabled={busy} className="mt-1 h-4 w-4 accent-primary"/>{msg('FE_PASS_REFUND_ACK', 'I have reviewed this purchase and understand how the refund affects coverage.')}</label>{actionError && <p role="alert" className="text-sm text-destructive">{actionError}</p>}<button className={primary + ' w-full'} disabled={busy || !ack || !reason.trim()}>{msg('FE_PASS_REFUND_SAVE', 'Refund {amount} to wallet', {amount:money(receipt?.amount_kobo)})}</button></form></DialogContent></Dialog>
  </div>;
}
