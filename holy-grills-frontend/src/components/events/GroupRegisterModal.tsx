import { sessionStore } from '@/lib/storage';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, Users, X } from 'lucide-react';
import ModalPortal from '@/components/ModalPortal';
import { liveApi } from '@/lib/liveApi';
import { apiClient } from '@/lib/apiClient';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';
import EventAnswers, { eventAnswersComplete } from './EventAnswers';

const blank = () => ({ key: crypto.randomUUID(), email: '', tier_id: '' });
export default function GroupRegisterModal({ event, tiers: initialTiers, user, onClose }) {
  const navigate = useNavigate();
  const [tiers, setTiers] = useState(initialTiers);
  const cacheKey = `hg_event_group_attempt:${user?.id || 'guest'}:${event.id}`;
  const saved = useRef<any>(null);
  const [attendees, setAttendees] = useState([blank(), blank()]);
  const [buyer, setBuyer] = useState({ name: user?.full_name || '', email: user?.email || '', phone: user?.phone || '' });
  const [method, setMethod] = useState(user ? 'wallet' : 'card');
  const [wallet, setWallet] = useState('');
  const [promo, setPromo] = useState('');
  const [answers, setAnswers] = useState({});
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [recovering, setRecovering] = useState(() => {
    try { saved.current = JSON.parse(sessionStore.getItem(cacheKey) || 'null'); } catch { saved.current = null; }
    return !!saved.current;
  });
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [fields, setFields] = useState(Array.isArray(event.registration_fields) ? event.registration_fields : []);
  const update = (key, value) => setAttendees(rows => rows.map(row => row.key === key ? { ...row, ...value } : row));
  const total = attendees.reduce((sum, attendee) => { const tier = tiers.find(item => item.id === attendee.tier_id); return sum + Number(tier?.price_naira_full ?? tier?.price_naira ?? 0); }, 0);
  const submit = async (eventSubmit) => {
    eventSubmit.preventDefault();
    if (lock.current) return;
    if (!recovering && !eventAnswersComplete(fields, answers)) { setError(msg('FE_EVENT_GROUP_REQUIRED', 'Complete the required booking questions.')); return; }
    lock.current = true; setBusy(true); setError('');
    const body = saved.current || { buyer, registration_answers: answers, booking_notes: notes, attendees: attendees.map(({ key: _key, ...row }) => ({ ...row, tier_id: row.tier_id || null })), expected_subtotal: total, payment_method: method, wallet_amount: method === 'split' ? Number(wallet) : 0, promo_code: promo.trim(), idempotency_key: crypto.randomUUID() };
    saved.current = body; sessionStore.setItem(cacheKey, JSON.stringify(body));
    try {
      const result = await apiClient.post(`/events/${event.id}/groups`, body);
      if (!user) sessionStore.setItem(`hg_event_group_access:${result.id}`, result.access_token);
      sessionStore.removeItem(cacheKey);
      if (!mounted.current) return;
      navigate(`/events/${event.id}/group/${result.id}`);
      onClose();
    } catch (failure) {
      setError(failure.message || msg('EVENT_GROUP_FAILED', 'The group booking could not be completed. Retry the same booking before starting another.'));
      const uncertain = !failure.status || failure.status === 408 || failure.status >= 500;
      setRecovering(uncertain);
      if (!uncertain) { saved.current = null; sessionStore.removeItem(cacheKey); }
      if (Array.isArray(failure.detail?.registration_fields)) setFields(failure.detail.registration_fields);
      if (failure.status === 409) { try { setTiers(await liveApi.events.getTiers(event.id)); } catch { /* Keep the draft and original error visible. */ } }
    } finally { lock.current = false; setBusy(false); }
  };
  const control = 'mt-1 min-h-11 w-full rounded-xl border border-border bg-background p-3 text-sm';
  return <ModalPortal><div className="fixed inset-0 z-50 hg-scrim flex items-end sm:items-center justify-center p-3 sm:p-6" role="dialog" aria-modal="true" aria-label={msg('FE_EVENT_GROUP_TITLE', 'Book for a group')}><form onSubmit={submit} className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-card shadow-xl">
    <header className="flex items-start justify-between gap-3 bg-gradient-dark p-5 text-white"><div><Users aria-hidden="true" className="mb-2 h-6 w-6 text-accent" /><h2 className="font-heading text-xl font-bold">{msg('FE_EVENT_GROUP_TITLE', 'Book for a group')}</h2><p className="mt-2 text-sm text-white/75">{msg('FE_EVENT_GROUP_HELP', 'One payment, individual tickets. Each attendee gets their own QR and earns their own attendance HP.')}</p></div><button type="button" disabled={busy} onClick={onClose} aria-label={msg('FE_EVENT_GROUP_CLOSE', 'Close group booking')} className="rounded-full p-2"><X /></button></header>
    <div className="space-y-5 p-5">{error && <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm">{error}</p>}
    {recovering ? <p className="rounded-xl bg-secondary p-4 text-sm">{msg('FE_EVENT_GROUP_RECOVER_HELP', 'Your previous booking may already be saved. Recover it using the same details before starting another payment.')}</p> : <fieldset disabled={busy} className="space-y-5">
      <section className="space-y-3"><h3 className="font-bold">{msg('FE_EVENT_GROUP_BUYER', 'Purchaser details')}</h3>{['name', 'email', 'phone'].map(field => <label key={field} className="block text-sm">{msg(`FE_EVENT_GROUP_${field.toUpperCase()}`, field[0].toUpperCase() + field.slice(1))}<input required readOnly={field === 'email' && !!user} type={field === 'email' ? 'email' : field === 'phone' ? 'tel' : 'text'} maxLength={field === 'name' ? 200 : 254} className={control} value={buyer[field]} onChange={eventInput => setBuyer({ ...buyer, [field]: eventInput.target.value })} /></label>)}</section>
      <section className="space-y-3" aria-label={msg('FE_EVENT_GROUP_ATTENDEES', 'Attendees')}><p className="text-sm text-muted-foreground">{msg('FE_EVENT_GROUP_EMAIL_ONLY', 'Enter each recipient’s email. We send separate tickets to them and use your details as the booking contact.')}</p>{attendees.map((attendee, index) => <details key={attendee.key} open className="rounded-2xl border border-border bg-secondary/20 p-4"><summary className="cursor-pointer font-bold">{msg('FE_EVENT_GROUP_PERSON', 'Attendee {number}', { number: index + 1 })}{attendee.email ? ` · ${attendee.email}` : ''}</summary><div className="mt-4 space-y-3"><label className="block text-sm">{msg('FE_EVENT_GROUP_EMAIL', 'Email')}<input required type="email" maxLength={254} className={control} value={attendee.email} onChange={eventInput => update(attendee.key, { email: eventInput.target.value })} /></label>{tiers.length > 0 && <label className="block text-sm">{msg('FE_EVENT_GROUP_TIER', 'Ticket tier')}<select aria-label={msg('FE_EVENT_GROUP_TIER', 'Ticket tier')} required className={control} value={attendee.tier_id} onChange={eventInput => update(attendee.key, { tier_id: eventInput.target.value })}><option value="">{msg('FE_EVENT_GROUP_TIER_CHOOSE', 'Choose a ticket tier')}</option>{tiers.map(tier => <option key={tier.id} value={tier.id} disabled={tier.is_active === false || (tier.capacity != null && Number(tier.sold_count || 0) >= Number(tier.capacity)) || tier.remaining != null && tier.remaining <= 0}>{tier.name} · {formatNaira(tier.price_naira_full ?? tier.price_naira ?? 0)}</option>)}</select></label>}{attendees.length > 1 && <button type="button" onClick={() => setAttendees(rows => rows.filter(row => row.key !== attendee.key))} className="flex min-h-10 items-center gap-2 text-sm font-semibold text-destructive"><Trash2 className="h-4 w-4" />{msg('FE_EVENT_GROUP_REMOVE', 'Remove attendee')}</button>}</div></details>)}<button type="button" disabled={attendees.length >= 10} onClick={() => setAttendees(rows => [...rows, blank()])} className="flex min-h-11 items-center gap-2 rounded-full border border-border px-5 text-sm font-bold disabled:opacity-50"><Plus className="h-4 w-4" />{msg('FE_EVENT_GROUP_ADD', 'Add attendee')}</button></section>
      <section className="space-y-3"><h3 className="font-bold">{msg('FE_EVENT_GROUP_BOOKING_QUESTIONS', 'Booking details')}</h3><p className="text-sm text-muted-foreground">{msg('FE_EVENT_GROUP_SHARED_HELP', 'Answer once for this booking. These answers apply to the whole group. Use the notes for quantities or different preferences.')}</p><EventAnswers fields={fields} value={answers} onChange={setAnswers} /><label className="block text-sm">{msg('FE_EVENT_GROUP_NOTES', 'Group notes (optional)')}<textarea maxLength={5000} rows={3} value={notes} onChange={eventInput => setNotes(eventInput.target.value)} className={control} placeholder={msg('FE_EVENT_GROUP_NOTES_HINT', 'For example: 2 vegetarian meals and 3 regular meals.')} /></label></section>
      <p className="text-xs text-muted-foreground">{msg('FE_EVENT_GROUP_CASH_HELP', 'Group tickets use the full cash price. HP discounts remain available for individual registration. Each attendee keeps their own check-in rewards.')}</p>
      {total > 0 && <section className="space-y-3"><label className="block text-sm">{msg('FE_EVENT_GROUP_PAY_WITH', 'Payment method')}<select aria-label={msg('FE_EVENT_GROUP_PAY_WITH', 'Payment method')} value={method} onChange={eventInput => setMethod(eventInput.target.value)} className={control}>{(user ? ['wallet', 'card', 'split'] : ['card']).map(value => <option key={value} value={value}>{msg(`FE_EVENT_GROUP_PAY_${value.toUpperCase()}`, value)}</option>)}</select></label>{method === 'split' && <label className="block text-sm">{msg('FE_EVENT_GROUP_WALLET', 'Wallet contribution')}<input required type="number" min="0.01" max={Math.max(0, total - 0.01)} step="0.01" value={wallet} onChange={eventInput => setWallet(eventInput.target.value)} className={control} /></label>}<label className="block text-sm">{msg('FE_EVENT_GROUP_PROMO', 'Promo code (optional)')}<input value={promo} maxLength={100} onChange={eventInput => setPromo(eventInput.target.value)} className={control} /></label></section>}
      <div className="flex items-center justify-between rounded-2xl bg-secondary p-4"><strong>{msg('FE_EVENT_GROUP_TOTAL', 'Total before promo')}</strong><strong>{formatNaira(total)}</strong></div>
    </fieldset>}
    <button disabled={busy} className="min-h-12 w-full rounded-full bg-gradient-cta px-5 py-3 font-bold text-white disabled:opacity-50">{busy ? msg('FE_EVENT_GROUP_SAVING', 'Saving booking…') : recovering ? msg('FE_EVENT_GROUP_RECOVER', 'Recover group booking') : msg('FE_EVENT_GROUP_CONTINUE', 'Continue to group booking')}</button></div>
  </form></div></ModalPortal>;
}
