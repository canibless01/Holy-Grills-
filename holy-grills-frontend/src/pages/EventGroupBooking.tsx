import { sessionStore } from '@/lib/storage';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Users, CheckCircle2, Clock, Copy } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { isAllowedPaymentUrl } from '@/lib/safeNavigation';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';
import TicketQrImage from '@/components/events/TicketQrImage';

export default function EventGroupBooking() {
  const { id, groupId } = useParams();
  const { isAuthenticated, user } = useHolyGrill();
  const [group, setGroup] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [openTicket, setOpenTicket] = useState('');
  const [copied, setCopied] = useState(false);
  const lock = useRef(false);
  const scope = useRef(''); scope.current = `${id}:${groupId}:${user?.id || 'guest'}`;
  const access = () => new URLSearchParams(window.location.search).get('access') || (!isAuthenticated ? sessionStore.getItem(`hg_event_group_access:${groupId}`) : '') || '';
  const endpoint = `/events/${id}/groups/${groupId}`;
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setGroup(null);
    apiClient.get(endpoint, access() ? { access_token: access() } : {}).then(result => { if (active) { setGroup(result); if (!isAuthenticated) sessionStore.setItem(`hg_event_group_access:${groupId}`, result.access_token); } }).catch(failure => { if (active) setError(failure.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [endpoint, retry, groupId, isAuthenticated, user?.id]);
  const verify = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(''); const originalScope = scope.current;
    try { const result = await apiClient.post(endpoint + '/verify', { access_token: access() }); if (scope.current === originalScope) setGroup(result); }
    catch (failure) { if (scope.current === originalScope) setError(failure.message); }
    finally { lock.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (!group || group.payment_status !== 'pending' || !new URLSearchParams(window.location.search).has('reference')) return;
    let attempts = 0;
    void verify();
    const timer = window.setInterval(() => { if (++attempts >= 12) clearInterval(timer); else void verify(); }, 5000);
    return () => clearInterval(timer);
  }, [group?.id, group?.payment_status]); // Payment recovery stays tied to this booking.
  const pay = async () => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(''); const originalScope = scope.current;
    let redirecting = false;
    try {
      const result = await apiClient.post(endpoint + '/payment', { access_token: access() });
      if (scope.current !== originalScope) return;
      if (['paid', 'not_required'].includes(result.payment_status) && result.tickets) { setGroup(result); return; }
      if (!isAllowedPaymentUrl(result.authorization_url)) throw new Error(msg('EVENT_GROUP_PAYMENT_INVALID', 'The payment link could not be verified.'));
      redirecting = true;
      window.location.assign(result.authorization_url);
    } catch (failure) { if (scope.current === originalScope) setError(failure.message); }
    finally { if (!redirecting) { lock.current = false; setBusy(false); } }
  };

  const copy = async () => {
    try { const url = new URL(window.location.pathname, window.location.origin); url.searchParams.set('access', group.access_token); await navigator.clipboard.writeText(url.toString()); setCopied(true); }
    catch { setError(msg('FE_EVENT_GROUP_COPY_FAILED', 'The private link could not be copied. Keep this page open and retry.')); }
  };
  const confirmed = (group?.tickets || []).filter(ticket => ['paid', 'not_required'].includes(ticket.payment_status) && ['confirmed', 'checked_in'].includes(ticket.status));
  const expired = group?.expires_at && new Date(group.expires_at).getTime() <= Date.now();
  const pending = group?.payment_status === 'pending';
  return <main className="mx-auto max-w-2xl space-y-5 pb-8">
    <Link to={`/events/${id}`} className="inline-flex min-h-10 items-center text-sm font-semibold text-primary">{msg('FE_EVENT_GROUP_BACK', 'Back to event')}</Link>
    <header className="rounded-3xl bg-gradient-dark p-6 text-white"><Users className="mb-3 h-7 w-7 text-accent" aria-hidden="true" /><h1 className="font-heading text-2xl font-bold">{msg('FE_EVENT_GROUP_BOOKING', 'Your group booking')}</h1><p className="mt-2 text-sm text-white/75">{msg('FE_EVENT_GROUP_HELP', 'One payment, individual tickets. Each attendee gets their own QR and earns their own attendance HP.')}</p></header>
    {error && <div role="alert" className="rounded-2xl border border-destructive/30 bg-card p-4 text-sm">{error}</div>}
    {loading ? <p role="status">{msg('FE_EVENT_GROUP_LOADING', 'Loading group booking…')}</p> : !group ? <button onClick={() => setRetry(value => value + 1)} className="min-h-11 rounded-full bg-primary px-6 font-bold text-white">{msg('FE_PLATFORM_RETRY', 'Retry')}</button> : <>
      <section className="rounded-2xl border border-border bg-card p-5 space-y-3"><div className="flex items-center gap-2 font-bold">{pending ? <Clock className="h-5 w-5 text-primary" /> : <CheckCircle2 className="h-5 w-5 text-success" />}{pending ? msg('FE_EVENT_GROUP_PENDING', 'Payment not yet confirmed') : confirmed.length === 1 ? msg('FE_EVENT_GROUP_CONFIRMED_ONE', '1 ticket confirmed') : msg('FE_EVENT_GROUP_CONFIRMED', '{count} tickets confirmed', { count: confirmed.length })}</div><div className="flex justify-between text-sm"><span>{msg('FE_EVENT_GROUP_AMOUNT', 'Booking total')}</span><strong>{formatNaira(group.total)}</strong></div>{Number(group.wallet_amount) > 0 && <div className="flex justify-between text-sm"><span>{msg('FE_EVENT_GROUP_WALLET_USED', 'Wallet contribution')}</span><span>{formatNaira(group.wallet_amount)}</span></div>}{Number(group.card_amount) > 0 && <div className="flex justify-between text-sm"><span>{msg('FE_EVENT_GROUP_CARD_AMOUNT', 'Card contribution')}</span><span>{formatNaira(group.card_amount)}</span></div>}
      {pending && <div className="space-y-3 border-t border-border pt-3"><p className="text-sm text-muted-foreground">{expired ? msg('EVENT_GROUP_EXPIRED', 'This reservation has expired or changed. Do not pay it again. Check each ticket’s status or contact support.') : msg('FE_EVENT_GROUP_PENDING_HELP', 'Places are reserved temporarily. Tickets and entry QR codes are issued only after payment is confirmed.')}</p>{!expired && <button disabled={busy} onClick={pay} className="min-h-12 w-full rounded-full bg-gradient-cta px-5 py-3 font-bold text-white disabled:opacity-50">{msg('FE_EVENT_GROUP_PAY', 'Pay {amount}', { amount: formatNaira(group.card_amount) })}</button>}<button disabled={busy} onClick={verify} className="min-h-11 w-full rounded-full border border-border px-5 font-bold disabled:opacity-50">{msg('FE_EVENT_GROUP_VERIFY', 'I have paid — check payment')}</button></div>}</section>
      <section className="space-y-3" aria-label={msg('FE_EVENT_GROUP_ATTENDEES', 'Attendees')}>{group.tickets.map(ticket => <article key={ticket.id} className="rounded-2xl border border-border bg-card p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-bold break-words">{ticket.name}</h2><span className="rounded-full bg-secondary px-3 py-1 text-xs font-bold">{msg(`FE_EVENT_GROUP_STATUS_${ticket.status.toUpperCase()}`, ticket.status)}</span></div><p className="mt-1 break-words text-sm text-muted-foreground">{ticket.email}</p><p className="mt-1 text-xs text-muted-foreground">{ticket.tier_name} · {formatNaira(ticket.price)}</p>{ticket.access_token && <div className="mt-3"><button onClick={() => setOpenTicket(current => current === ticket.id ? '' : ticket.id)} className="min-h-11 rounded-full border border-border px-5 text-sm font-bold">{msg('FE_EVENT_GROUP_VIEW_TICKET', 'View ticket')}</button>{openTicket === ticket.id && <TicketQrImage eventId={id} ticketId={ticket.id} accessToken={ticket.access_token} />}</div>}</article>)}</section>
      <section className="space-y-3 rounded-2xl bg-secondary p-4 text-sm"><p>{msg('FE_EVENT_GROUP_EMAIL_HELP', 'Each attendee receives their own ticket by email after confirmation. Their verified account can claim the ticket and attendance HP. Keep this purchaser link private.')}</p><p>{msg('FE_EVENT_GROUP_REFUND_HELP', 'Support-approved refunds return to the purchaser’s Holy Grills wallet. Each attendee keeps their own ticket and attendance rewards.')}</p><button type="button" onClick={copy} className="flex min-h-11 items-center gap-2 rounded-full border border-border bg-card px-5 font-bold"><Copy className="h-4 w-4" />{copied ? msg('FE_EVENT_GROUP_COPIED', 'Private booking link copied') : msg('FE_EVENT_GROUP_COPY', 'Copy private booking link')}</button>{!isAuthenticated && <Link to="/signup" className="inline-flex min-h-11 items-center font-bold text-primary">{msg('FE_EVENT_GROUP_SIGNUP', 'Create an account to manage your bookings')}</Link>}</section>
    </>}
  </main>;
}
