import { useRef, useState } from 'react';
import { CalendarClock, MapPin } from 'lucide-react';
import { eventOrganizerApi } from '@/lib/eventOrganizerApi';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { confirmAction } from '@/lib/confirmAction';
import { msg } from '@/lib/messages';

const wat = (value: string) => value ? new Date(new Date(value).getTime() + 3600000).toISOString().slice(0, 16) : '';
const inputClass = 'w-full rounded-xl border border-border bg-background p-3 text-sm';

export default function EventOperationControls({ event, onSaved, disabled = false }: { event: any; onSaved: () => void; disabled?: boolean }) {
  const [action, setAction] = useState('reschedule');
  const [starts, setStarts] = useState(wat(event.starts_at));
  const [ends, setEnds] = useState(wat(event.ends_at));
  const [location, setLocation] = useState(event.location || '');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const lock = useRef(false);
  const intent = useCmsCreateIntent();
  const pendingVersion = useRef<{ id: string; version: string } | null>(null);
  const cancelled = event.metadata?.lifecycle_status === 'cancelled';
  const policy = msg('FE_EVENT_CANCEL_POLICY', 'Unused paid tickets receive a refund of the ticket amount paid; separately charged payment-provider fees are excluded. Account purchases return to the Holy Grills wallet with spent HP restored; guest card refunds return through the payment provider. Provider confirmation can take time. Checked-in tickets are excluded. Payments confirmed after cancellation are refunded too.');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (lock.current || disabled) return;
    lock.current = true;
    setBusy(true); setError(''); setNotice('');
    try {
      if (action === 'cancel' && !await confirmAction({ title: msg('FE_EVENT_CANCEL_CONFIRM', 'Cancel this event and refund unused paid tickets?'), body: policy, destructive: true, confirmLabel: msg('FE_EVENT_CANCEL_BUTTON', 'Cancel event') })) return;
      const body = intent.body({ action, reason: reason.trim(), ...(action === 'reschedule' ? { starts_at: starts, ends_at: ends, location: location.trim() } : {}) });
      if (pendingVersion.current?.id !== body.request_id) pendingVersion.current = { id: body.request_id, version: event.updated_at };
      const result = await eventOrganizerApi.change(event.id, { ...body, expected_updated_at: pendingVersion.current.version });
      intent.clear(); pendingVersion.current = null;
      setNotice(action === 'cancel' ? msg('FE_EVENT_CANCEL_RESULT', 'Event cancelled. Refunds recorded: {count}. Any pending payments will be refunded if confirmed.', { count: result.refunds }) : msg('FE_EVENT_RESCHEDULE_RESULT', 'Schedule updated. Existing tickets remain valid and attendee notices have been queued.'));
      onSaved();
    } catch (err) { setError(err.message); if (err.detail?.code === 'event_changed') { intent.clear(); pendingVersion.current = null; onSaved(); } }
    finally { lock.current = false; setBusy(false); }
  };

  return <section aria-label={msg('FE_EVENT_OPERATIONS', 'Schedule and cancellation')} className="space-y-4 rounded-2xl border border-border bg-card p-4 sm:p-5">
    <div className="flex items-center gap-2"><CalendarClock className="h-5 w-5 text-primary" /><h3 className="font-heading font-extrabold">{msg('FE_EVENT_OPERATIONS', 'Schedule and cancellation')}</h3></div>
    <p className="text-xs leading-relaxed text-muted-foreground">{msg('FE_EVENT_OPERATIONS_HELP', 'Use these controls for published events so ticket changes and attendee notices are recorded together. Rescheduling is available before check-in begins.')}</p>
    {cancelled ? <div className="space-y-2 rounded-xl bg-destructive/5 p-3"><p className="font-bold text-destructive">{msg('FE_EVENT_CANCELLED', 'Event cancelled')}</p><p className="text-sm">{event.metadata.change_reason}</p><p className="text-xs leading-relaxed text-muted-foreground">{policy}</p></div> : <form onSubmit={submit} className="space-y-3">
      <fieldset disabled={busy || disabled || event.review_status !== 'approved'} className="space-y-3 disabled:opacity-60">
        <label className="block space-y-1 text-xs font-bold">{msg('FE_EVENT_CHANGE_ACTION', 'Event action')}<select aria-label={msg('FE_EVENT_CHANGE_ACTION', 'Event action')} className={inputClass} value={action} onChange={e => setAction(e.target.value)}><option value="reschedule">{msg('FE_EVENT_RESCHEDULE', 'Reschedule event')}</option><option value="cancel">{msg('FE_EVENT_CANCEL_BUTTON', 'Cancel event')}</option></select></label>
        {action === 'reschedule' ? <><div className="grid gap-3 sm:grid-cols-2"><label className="block space-y-1 text-xs font-bold">{msg('FE_ORG_START', 'Starts (WAT)')}<input type="datetime-local" required className={inputClass} value={starts} onChange={e => setStarts(e.target.value)} /></label><label className="block space-y-1 text-xs font-bold">{msg('FE_ORG_END', 'Ends (WAT)')}<input type="datetime-local" required className={inputClass} value={ends} onChange={e => setEnds(e.target.value)} /></label></div><label className="block space-y-1 text-xs font-bold"><span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{msg('FE_ORG_LOCATION', 'Venue / location')}</span><input required maxLength={500} className={inputClass} value={location} onChange={e => setLocation(e.target.value)} /></label></> : <p className="rounded-xl bg-destructive/5 p-3 text-xs leading-relaxed">{policy}</p>}
        <label className="block space-y-1 text-xs font-bold">{msg('FE_EVENT_CHANGE_REASON', 'Reason sent to attendees')}<textarea aria-label={msg('FE_EVENT_CHANGE_REASON', 'Reason sent to attendees')} required minLength={10} maxLength={500} rows={3} className={inputClass} value={reason} onChange={e => setReason(e.target.value)} /></label>
        <button type="submit" className={`min-h-11 w-full rounded-full px-4 py-3 text-sm font-bold text-white sm:w-auto ${action === 'cancel' ? 'bg-destructive' : 'bg-gradient-cta'}`}>{busy ? msg('FE_ORG_SAVING', 'Saving…') : action === 'cancel' ? msg('FE_EVENT_CANCEL_BUTTON', 'Cancel event') : msg('FE_EVENT_SAVE_SCHEDULE', 'Save new schedule')}</button>
      </fieldset>
    </form>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}{notice && <p role="status" className="text-sm text-success">{notice}</p>}
  </section>;
}
