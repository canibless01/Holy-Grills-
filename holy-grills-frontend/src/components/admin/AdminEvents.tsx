import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect, useRef } from 'react';
import { Plus, Pencil, Trash2, Eye, QrCode, Ticket, Download, Mail, BarChart3 } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import { apiClient } from '@/lib/apiClient';
import { safeText } from '@/lib/valueText';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { msg } from '@/lib/messages';
import EventCheckInScanner from '@/components/EventCheckInScanner';
import { csvCell } from '@/lib/csvCell';
import { useHolyGrill } from '@/lib/HolyGrillContext';

const BLANK = { title: '', description: '', location: '', starts_at: '', ends_at: '', hp_reward: 30, hp_per_attendee: 30, max_attendees: 100, funding_source: 'hg_funded', is_paid: false, is_featured: false, is_published: false, image_url: '' };

const watInput = (value) => {
  if (!value) return '';
  const instant = new Date(value);
  return Number.isNaN(instant.getTime()) ? '' : new Date(instant.getTime() + 3600000).toISOString().slice(0, 16);
};

export default function AdminEvents() {
  const { user } = useHolyGrill();
  const { campusId, adminCampusId } = useCampus();
  const eventScope = useRef(0);
  const eventLoad = useRef(0);
  const panelLoad = useRef(0);
  const writing = useRef(false);
  const admissionLock = useRef(false);
  const [offset, setOffset] = useState(0);
  const pageSize = 25;
  const [scannerEvent, setScannerEvent] = useState<string | null>(null);
  const [admitting, setAdmitting] = useState(false);
  const [admissionMessage, setAdmissionMessage] = useState('');
  const [admissionError, setAdmissionError] = useState('');
  const historyLoad = useRef(0);
  const canManage = (event) => user?.role === 'super_admin' || (!!event.campus_id && event.campus_id === (user?.campus_id || user?.profile?.campus_id));
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [regs, setRegs] = useState(null);
  const [qr, setQr] = useState(null);
  const [tiersModal, setTiersModal] = useState(null);
  const [salesModal, setSalesModal] = useState(null);
  const [emailModal, setEmailModal] = useState(null);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [refund, setRefund] = useState<any>(null);
  const [refundHistory, setRefundHistory] = useState<any>(null);
  const [refundReview, setRefundReview] = useState<any>(null);
  const [refundBusy, setRefundBusy] = useState(false);
  const [refundError, setRefundError] = useState('');
  const openRefundHistory = async (eventId: string) => {
    const version = ++historyLoad.current;
    setRefundHistory({eventId, rows:[], loading:true, error:false});
    try {
      const result = await apiClient.get(`/events/${eventId}/refunds`);
      if (version !== historyLoad.current) return;
      setRefundHistory(previous => previous?.eventId === eventId ? {eventId, rows:result.refunds || [], loading:false, error:false} : previous);
    } catch { if (version !== historyLoad.current) return; setRefundHistory(previous => previous?.eventId === eventId ? {...previous, loading:false, error:true} : previous); }
  };
  const requestRefund = async (event: React.FormEvent) => {
    event.preventDefault(); if (!refund || refundBusy) return;
    const scope = eventScope.current;
    setRefundBusy(true); setRefundError('');
    try {
      const result = await apiClient.post(`/events/${refund.eventId}/tickets/${refund.ticket.ticket_id}/refund`, {request_id:refund.id,reason:refund.reason.trim()});
      if (scope !== eventScope.current) return;
      toast({title:result.destination === 'wallet' ? 'Ticket refunded to wallet' : 'Guest refund queued',description:result.destination === 'wallet' ? 'Cash and spent HP have been returned.' : 'The refund will return to the original payment method after Paystack processes it.'});
      setRefund(null); setRegs(null); await openRefundHistory(refund.eventId);
    } catch { if (scope !== eventScope.current) return; setRefundError('Refund could not be confirmed. Retry with this request or refresh the ticket status.'); }
    finally { setRefundBusy(false); }
  };
  const saveRefundReview = async (event: React.FormEvent) => {
    event.preventDefault(); if (!refundReview || refundBusy) return;
    const scope = eventScope.current;
    setRefundBusy(true); setRefundError('');
    try {
      await apiClient.post(`/events/${refundReview.eventId}/refunds/${refundReview.row.id}/review`, {
        review_id:refundReview.id,outcome:refundReview.outcome,provider_refund_id:refundReview.providerId.trim() || null,evidence:refundReview.evidence.trim(),
      });
      if (scope !== eventScope.current) return;
      setRefundReview(null); await openRefundHistory(refundReview.eventId);
    } catch { if (scope !== eventScope.current) return; setRefundError('Provider review could not be saved. Refresh the refund and check your evidence.'); }
    finally { setRefundBusy(false); }
  };

  const load = async () => {
    const version = ++eventLoad.current; setLoading(true); setLoadError(false);
    try { const rows = await mockApi.admin.getEvents({ limit: pageSize, offset, ...(adminCampusId ? {campus_id: adminCampusId} : {}) }); if (version === eventLoad.current) setEvents(rows); }
    catch { if (version === eventLoad.current) setLoadError(true); }
    finally { if (version === eventLoad.current) setLoading(false); }
  };
  useEffect(() => {
    eventScope.current++; historyLoad.current++; panelLoad.current++;
    setOffset(0); setRegs(null); setModal(null); setQr(null); setTiersModal(null); setSalesModal(null); setEmailModal(null); setScannerEvent(null);
    setRefund(null); setRefundHistory(null); setRefundReview(null); setRefundError(''); setAdmissionMessage(''); setAdmissionError('');
  }, [campusId, adminCampusId]);
  useEffect(() => { void load(); return () => {eventLoad.current++;}; }, [campusId, adminCampusId, offset]);

  const save = async () => {
    if (writing.current || !modal) return;
    writing.current = true; const scope = eventScope.current;
    setBusy('save');
    const body = { ...modal.item, hp_reward: Number(modal.item.hp_reward), hp_per_attendee: Number(modal.item.hp_reward), max_attendees: Number(modal.item.max_attendees), capacity: Number(modal.item.max_attendees), is_featured: !!modal.item.is_featured, is_paid: !!modal.item.is_paid };
    try {
      let savedEvent = null;
      if (modal.isNew) { savedEvent = await mockApi.admin.createEvent(body); toast({ title: msg('FE_ADMIN_EVENTS_EVENT_CREATED', '✅ Event created'), description: msg('FE_EVENT_SAVED_TITLE', '"{title}" has been saved.', { title: body.title }) }); }
      else { await mockApi.admin.updateEvent(modal.item.id, body); savedEvent = { id: modal.item.id }; toast({ title: msg('FE_ADMIN_EVENTS_EVENT_UPDATED', '✅ Event updated'), description: msg('FE_ADMIN_EVENTS_TITLE_HAS_BEEN_SAVED', '"{title}" has been saved.', { title: body.title }) }); }
      if (scope !== eventScope.current) return;
      setModal(null); await load();
    } catch (e) { if (scope !== eventScope.current) return; toast({ title: msg('FE_ADMIN_EVENTS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };

  const togglePub = async (event) => {
    if (writing.current) return;
    writing.current = true; setBusy(event.id);
    const scope = eventScope.current;
    try { await mockApi.admin.updateEvent(event.id, {is_published: !event.is_published}); if (scope !== eventScope.current) return; toast({ title: msg('FE_ADMIN_EVENTS_PUBLISH_STATUS_TOGGLED', 'Publish status toggled') }); await load(); }
    catch (e) { if (scope === eventScope.current) toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };

  const remove = async (id) => {
    if (await confirmAction({ title: "Delete event?", destructive: true, confirmLabel: "Delete" })) {
      try { await mockApi.admin.deleteEvent(id); toast({ title: msg('FE_ADMIN_EVENTS_EVENT_DELETED', 'Event deleted') }); await load(); }
      catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    }
  };

  const readPanel = async (id, setter, reader, key) => {
    const version = ++panelLoad.current;
    setter({eventId:id, [key]:[], loading:true, error:false, tierFilter:'', checkinFilter:'', search:''});
    try {
      const result = await reader(id);
      if (version === panelLoad.current) setter({eventId:id, [key]:result, loading:false, error:false, tierFilter:'', checkinFilter:'', search:''});
    } catch {
      if (version === panelLoad.current) setter({eventId:id, [key]:[], loading:false, error:true, tierFilter:'', checkinFilter:'', search:''});
    }
  };
  const viewRegs = (id) => readPanel(id, setRegs, mockApi.admin.getEventRegistrants, 'data');
  const viewTiers = (id) => readPanel(id, setTiersModal, mockApi.admin.getEventTicketTiers, 'tiers');
  const viewSales = (id) => readPanel(id, setSalesModal, mockApi.admin.getEventTicketSales, 'data');
  const genQR = async (id) => {
    if (writing.current) return;
    if (!(await confirmAction({ title: msg('FE_EVENT_QR_ROTATE', 'Generate a new venue QR? Previous venue codes will stop working.'), confirmLabel: msg('FE_EVENT_GENERATE_QR', 'Generate QR') }))) return;
    if (writing.current) return;
    writing.current = true; setBusy(id); const scope = eventScope.current;
    try { const result = await mockApi.admin.generateEventQR(id); if (scope === eventScope.current) setQr(result); }
    catch (e) { if (scope === eventScope.current) toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };
  const admitTicket = async (eventId, token) => {
    if (admissionLock.current) return;
    admissionLock.current = true; setAdmitting(true); setAdmissionError(''); setAdmissionMessage('');
    const scope = eventScope.current; const panel = panelLoad.current;
    try {
      const result = await apiClient.post(`/events/${eventId}/checkin`, {qr_token: token});
      if (scope !== eventScope.current) return;
      setAdmissionMessage(result.replayed ? msg('FE_EVENT_ALREADY_ADMITTED', 'This ticket was already checked in. No additional HP was awarded.') : msg('FE_EVENT_ADMITTED', 'Check-in recorded. Attendee HP: {hp}.', {hp:result.hp_added_to_active || 0}));
      if (panel === panelLoad.current) await viewRegs(eventId);
    } catch (e) { if (scope === eventScope.current) setAdmissionError(e.message || msg('FE_EVENT_ADMIT_FAILED', 'Check-in could not be confirmed. Retry the same ticket.')); }
    finally { admissionLock.current = false; setAdmitting(false); }
  };

  const exportRegs = async (eventId) => {
    if (writing.current) return;
    writing.current = true; setBusy('export');
    const scope = eventScope.current;
    try {
      // TODO(ts): the export endpoint's envelope varies (rows/data/registrants/array).
       
      const res: any = await mockApi.admin.exportEventRegistrations(eventId);
      if (scope !== eventScope.current) return;
      const rows = res?.rows || res?.data || res?.registrants || (Array.isArray(res) ? res : []);
      if (!rows.length) { toast({ title: msg('FE_ADMIN_EVENTS_NO_REGISTRANTS_TO_EXPORT', 'No registrants to export'), description: msg('FE_ADMIN_EVENTS_THE_EXPORT_ENDPOINT_RETURNED_NO_DATA', 'The export endpoint returned no data.'), variant: 'destructive' }); return; }
      const headers = Object.keys(rows[0]);
      const csv = [headers.join(','), ...rows.map(r => headers.map(h => `"${csvCell(r[h])}"`).join(','))].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `event_${eventId}_registrations.csv`; a.click();
      URL.revokeObjectURL(url);
      toast({ title: msg('FE_ADMIN_EVENTS_CSV_EXPORTED', '✅ CSV exported'), description: `${rows.length} registrants downloaded.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_EXPORT_FAILED', 'Export failed'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };

  const emailToHost = async (eventId, hostEmail) => {
    setSendingEmail(true);
    try {
      await mockApi.admin.emailEventRegistrationsToHost(eventId, { host_email: hostEmail });
      toast({ title: msg('FE_ADMIN_EVENTS_SENT_TO_HOST', '✅ Sent to host'), description: `Registrant list emailed to ${hostEmail}.` });
      setEmailModal(null);
    }
    catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED_TO_SEND', 'Failed to send'), description: e.message, variant: 'destructive' }); }
    setSendingEmail(false);
  };

  if (loading) return <StaffPanelSkeleton />;
  if (loadError) return <div className="text-center py-10 space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;

  const filteredRegs = regs ? regs.data.filter(r => {
    if (regs.search && ![r.full_name, r.email, r.phone, r.ticket_id].some(value => String(value || '').toLowerCase().includes(regs.search.trim().toLowerCase()))) return false;
    if (regs.tierFilter && (r.tier_name || r.tier || '') !== regs.tierFilter) return false;
    if (regs.checkinFilter === 'yes' && !r.checked_in) return false;
    if (regs.checkinFilter === 'no' && r.checked_in) return false;
    return true;
  }) : [];
  const tierOptions: string[] = regs ? ([...new Set(regs.data.map((r) => r.tier_name || r.tier).filter(Boolean))] as string[]) : [];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setModal({ item: { ...BLANK }, isNew: true })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add Event</button>
      </div>
      <div className="flex justify-between text-xs font-bold">
        <button disabled={offset === 0 || !!busy} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>{msg('FE_EVENT_PREVIOUS', 'Previous events')}</button>
        <button onClick={load} disabled={!!busy}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button>
        <button disabled={events.length < pageSize || !!busy} onClick={() => setOffset(value => value + pageSize)}>{msg('FE_EVENT_NEXT', 'Next events')}</button>
      </div>
      {events.map((e) => (
        <div key={e.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-2 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-sm text-foreground">{e.title}</span>
              {e.is_published ? <Pill tone="green">Published</Pill> : <Pill tone="amber">Draft</Pill>}
              {e.is_featured && <Pill tone="flame">Featured</Pill>}
              {e.is_paid && <Pill tone="blue">Paid</Pill>}
            </div>
            <div className="text-xs text-muted-foreground">{e.location} · {e.checkin_count}/{e.capacity ?? e.max_attendees ?? '∞'} checked in · {e.hp_reward ?? e.hp_per_attendee} HP</div>
          </div>
          {canManage(e) && <Toggle checked={e.is_published} disabled={!!busy} onChange={() => togglePub(e)} />}
          <button disabled={!canManage(e)} onClick={() => viewTiers(e.id)} title="Ticket Tiers" className="p-2 rounded-lg hover:bg-muted"><Ticket className="w-4 h-4 text-purple-500" /></button>
          <button onClick={() => viewSales(e.id)} title="Sales Dashboard" className="p-2 rounded-lg hover:bg-muted"><BarChart3 className="w-4 h-4 text-success" /></button>
          <button disabled={!canManage(e)} onClick={() => viewRegs(e.id)} title="Registrants" className="p-2 rounded-lg hover:bg-muted"><Eye className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => void openRefundHistory(e.id)} title="Refund history" className="text-primary text-xs font-bold p-2">Refunds</button>
          <button disabled={!canManage(e)} onClick={() => genQR(e.id)} title="QR" className="p-2 rounded-lg hover:bg-muted"><QrCode className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => setModal({ item: { ...e, hp_reward: e.hp_per_attendee ?? e.hp_reward ?? 0, max_attendees: e.capacity ?? e.max_attendees ?? '', starts_at: watInput(e.starts_at), ends_at: watInput(e.ends_at) }, isNew: false })} title={msg('FE_EVENT_EDIT', 'Edit event')} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => remove(e.id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
        </div>
      ))}

      <Modal open={!!refund} onClose={() => {if (!refundBusy) setRefund(null);}} title="Refund entire ticket">
        {refund && <form onSubmit={requestRefund} className="space-y-4">
          <p className="text-sm">{refund.ticket.full_name || refund.ticket.email}</p>
          <p className="text-sm">₦{Number(refund.ticket.refund_amount || 0).toLocaleString()} {refund.ticket.is_guest ? 'will return to the original payment method after processing.' : 'will return to the Holy Grills wallet.'} {Number(refund.ticket.hp_paid || 0) > 0 && `${refund.ticket.hp_paid} spent HP will also be returned.`}</p>
          <p className="text-xs text-muted-foreground">The ticket will be cancelled and cannot be used for entry. Refunds are allowed only before check-in.</p>
          <Field label="Refund reason"><textarea required minLength={10} maxLength={500} disabled={refundBusy} className="w-full rounded-xl border border-border bg-card p-3" value={refund.reason} onChange={e => setRefund({...refund,reason:e.target.value,id:crypto.randomUUID()})} /></Field>
          {refundError && <p role="alert" className="text-destructive text-sm">{refundError}</p>}
          <button type="submit" disabled={refundBusy || refund.reason.trim().length < 10} className="rounded-full bg-primary text-white font-bold p-3 w-full disabled:opacity-50">{refundBusy ? 'Submitting...' : 'Confirm full refund'}</button>
        </form>}
      </Modal>
      <Modal open={!!refundHistory} onClose={() => setRefundHistory(null)} title="Ticket refunds">
        {refundHistory && <div className="space-y-3">
          <button type="button" disabled={refundHistory.loading} className="text-primary font-bold text-sm" onClick={() => void openRefundHistory(refundHistory.eventId)}>Refresh refunds</button>
          {refundHistory.loading ? <p>Loading refunds...</p> : refundHistory.error ? <p role="alert">Refunds could not load. Please refresh.</p> : refundHistory.rows.length === 0 ? <p>No refunds for this event.</p> : refundHistory.rows.map(row => <div key={row.id} className="border border-border rounded-xl p-3 space-y-1 break-words">
            <p className="font-bold text-sm">{row.recipient_name || row.recipient_email}</p>
            <p className="text-sm">₦{Number(row.amount).toLocaleString()} · {row.destination === 'wallet' ? 'Holy Grills wallet' : 'Original payment method'} · {row.state}</p>
            {row.provider_refund_id && <p className="text-xs">Paystack refund ID: {row.provider_refund_id}</p>}
            {row.error && <p className="text-xs text-muted-foreground">{row.error}</p>}
            {row.destination === 'paystack' && ['uncertain','failed'].includes(row.state) && <button type="button" className="text-primary font-bold text-xs" onClick={() => {setRefundError('');setRefundReview({eventId:refundHistory.eventId,row,id:crypto.randomUUID(),outcome:'lookup',providerId:row.provider_refund_id || '',evidence:''});}}>Review gateway result</button>}
          </div>)}
        </div>}
      </Modal>
      <Modal open={!!refundReview} onClose={() => {if (!refundBusy) setRefundReview(null);}} title="Review guest refund">
        {refundReview && <form onSubmit={saveRefundReview} className="space-y-4">
          <p className="text-sm">Check Paystack before retrying. Supplying a refund ID verifies its original transaction and amount; it does not mark a refund complete on your word alone.</p>
          <Field label="Provider result"><select disabled={refundBusy} className="w-full p-3 rounded-xl border border-border bg-card" value={refundReview.outcome} onChange={e => setRefundReview({...refundReview,outcome:e.target.value,id:crypto.randomUUID()})}>
            <option value="lookup">A Paystack refund exists — verify its ID</option>
            {!refundReview.row.provider_refund_id && <option value="not_sent">Paystack confirms no refund was created — queue again</option>}
          </select></Field>
          {refundReview.outcome === 'lookup' && <Field label="Paystack refund ID"><TextInput required pattern="[0-9]{1,30}" maxLength={30} disabled={refundBusy} value={refundReview.providerId} onChange={e => setRefundReview({...refundReview,providerId:e.target.value,id:crypto.randomUUID()})} /></Field>}
          <Field label="Provider log evidence"><textarea required minLength={10} maxLength={500} disabled={refundBusy} className="w-full p-3 rounded-xl border border-border bg-card" value={refundReview.evidence} onChange={e => setRefundReview({...refundReview,evidence:e.target.value,id:crypto.randomUUID()})} /></Field>
          {refundError && <p role="alert" className="text-destructive text-sm">{refundError}</p>}
          <button type="submit" disabled={refundBusy || refundReview.evidence.trim().length < 10} className="rounded-full bg-primary text-white p-3 w-full font-bold disabled:opacity-50">{refundBusy ? 'Saving...' : 'Save gateway review'}</button>
        </form>}
      </Modal>

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.isNew ? 'New Event' : 'Edit Event'}>
        {modal && (
          <div className="space-y-3">
            <Field label="Title"><TextInput value={modal.item.title} onChange={(e) => setModal({ item: { ...modal.item, title: e.target.value }, isNew: modal.isNew })} /></Field>
            <Field label="Description"><textarea value={modal.item.description} onChange={(e) => setModal({ item: { ...modal.item, description: e.target.value }, isNew: modal.isNew })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
            <Field label="Location"><TextInput value={modal.item.location} onChange={(e) => setModal({ item: { ...modal.item, location: e.target.value }, isNew: modal.isNew })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={msg('FE_EVENT_START_WAT', 'Starts (WAT)')}><TextInput type="datetime-local" value={modal.item.starts_at} onChange={(e) => setModal({ item: { ...modal.item, starts_at: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label={msg('FE_EVENT_END_WAT', 'Ends (WAT)')}><TextInput type="datetime-local" value={modal.item.ends_at} onChange={(e) => setModal({ item: { ...modal.item, ends_at: e.target.value }, isNew: modal.isNew })} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="HP Reward (per attendee)"><TextInput type="number" value={modal.item.hp_reward} onChange={(e) => setModal({ item: { ...modal.item, hp_reward: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label="Max attendees"><TextInput type="number" value={modal.item.max_attendees} onChange={(e) => setModal({ item: { ...modal.item, max_attendees: e.target.value }, isNew: modal.isNew })} /></Field>
            </div>
            <Field label="Funding Source">
              <select value={modal.item.funding_source} onChange={(e) => setModal({ item: { ...modal.item, funding_source: e.target.value }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                <option value="hg_funded">HG Funded</option>
                <option value="host_prepaid">Host Funded</option>
              </select>
            </Field>
            <p className="text-xs text-muted-foreground">{msg('FE_EVENT_PRICING_TIERS', 'Set ticket prices and HP discounts in Ticket Tiers after saving the event.')}</p>
            <Field label="Image"><ImageUploader value={modal.item.image_url} onChange={(url) => setModal({ item: { ...modal.item, image_url: url }, isNew: modal.isNew })} folder="events" /></Field>
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2"><Toggle checked={!!modal.item.is_published} onChange={(value) => setModal({...modal,item:{...modal.item,is_published:value}})} /><span className="text-sm font-semibold">{msg('FE_EVENT_PUBLISHED', 'Published')}</span></div>
              <div className="flex items-center gap-2"><Toggle checked={!!modal.item.is_featured} onChange={(v) => setModal({ item: { ...modal.item, is_featured: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">Featured</span></div>
              <div className="flex items-center gap-2"><Toggle checked={!!modal.item.is_paid} onChange={(v) => setModal({ item: { ...modal.item, is_paid: v }, isNew: modal.isNew })} /><span className="text-sm text-foreground font-semibold">Paid Event</span></div>
            </div>
            <p className="text-xs text-muted-foreground">Use the Ticket Tiers button on each event to add multiple ticket sizes (Regular, VIP, etc.)</p>
            <button onClick={save} disabled={busy === 'save'} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2">
              {busy === 'save' ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Saving...</> : (modal.isNew ? 'Create Event' : 'Save Changes')}
            </button>
          </div>
        )}
      </Modal>

      <Modal open={!!regs} onClose={() => {panelLoad.current++;setRegs(null);}} title="Event Registrants">
        {regs && <div className="space-y-3">
          {regs.loading ? <p role="status">{msg('FE_EVENT_LOADING', 'Loading event details…')}</p> : regs.error ? <div role="alert"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={() => viewRegs(regs.eventId)}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div> : <>
          <input aria-label={msg('FE_EVENT_FIND_ATTENDEE', 'Find attendee')} placeholder={msg('FE_EVENT_FIND_ATTENDEE_HELP', 'Name, email, phone or ticket ID')} value={regs.search} onChange={event => setRegs({...regs,search:event.target.value})} className="w-full p-3 border border-border rounded-xl" />
          <button disabled={admitting} onClick={() => setScannerEvent(regs.eventId)} className="font-bold text-primary">{msg('FE_EVENT_SCAN_ATTENDEE', 'Scan attendee ticket')}</button>
          {admissionMessage && <p role="status">{admissionMessage}</p>}{admissionError && <p role="alert" className="text-destructive">{admissionError}</p>}
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => exportRegs(regs.eventId)} disabled={busy === 'export'} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-secondary text-foreground text-xs font-bold disabled:opacity-50"><Download className="w-3.5 h-3.5" /> {busy === 'export' ? 'Exporting...' : 'Export CSV'}</button>
              <button onClick={() => setEmailModal({ eventId: regs.eventId, email: '' })} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Mail className="w-3.5 h-3.5" /> Send to Host</button>
            </div>
            <div className="flex gap-2">
              <select value={regs.tierFilter} onChange={(e) => setRegs({ ...regs, tierFilter: e.target.value })} className="p-2 rounded-lg border border-border text-xs">
                <option value="">All Tiers</option>
                {tierOptions.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <select value={regs.checkinFilter} onChange={(e) => setRegs({ ...regs, checkinFilter: e.target.value })} className="p-2 rounded-lg border border-border text-xs">
                <option value="">All</option>
                <option value="yes">Checked In</option>
                <option value="no">Not Checked In</option>
              </select>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {filteredRegs.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">No registrants match your filters.</p>
              ) : filteredRegs.map((r) => (
                <div key={r.ticket_id || r.id} className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 p-2.5 rounded-lg bg-muted text-sm">
                  <div className="min-w-0">
                    <div className="font-bold text-foreground">{r.full_name || r.name || 'Attendee'}</div>
                    <div className="text-xs text-muted-foreground truncate">{r.email || '—'} · {r.ticket_id || '—'}</div>
                  </div>
                  <div className="flex items-center flex-wrap gap-2 shrink-0">
                    {safeText(r.tier_name || r.tier, '') && <Pill tone="blue">{safeText(r.tier_name || r.tier, '')}</Pill>}
                    {r.checked_in ? <Pill tone="green">✓ Checked in</Pill> : <Pill tone="cocoa">Registered</Pill>}
                    {!r.checked_in && r.status === 'confirmed' && ['paid','not_required'].includes(r.payment_status) && <button disabled={admitting} className="text-primary font-bold text-xs" onClick={() => void admitTicket(regs.eventId, `hg-event:${regs.eventId}:${r.ticket_id}`)}>{msg('FE_EVENT_CHECK_IN_ATTENDEE', 'Check in attendee')}</button>}
                    {r.refundable && <button type="button" className="text-destructive font-bold text-xs" onClick={() => {setRefundError('');setRefund({eventId:regs.eventId,ticket:r,id:crypto.randomUUID(),reason:''});}}>Refund ticket</button>}
                  </div>
                </div>
              ))}
            </div>
          </>}
          </div>}
      </Modal>

      <Modal open={!!salesModal} onClose={() => {panelLoad.current++;setSalesModal(null);}} title="Ticket Sales Dashboard">
        {salesModal && (
          <div className="space-y-3">
            {salesModal.loading && <p role="status">{msg('FE_EVENT_LOADING', 'Loading event details…')}</p>}
            {salesModal.error && <div role="alert"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={() => viewSales(salesModal.eventId)}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>}
            {(() => {
              if (salesModal.loading || salesModal.error) return null;
              const tiers = salesModal.data?.tiers || salesModal.data?.sales || [];

              const totalSold = salesModal.data?.summary?.confirmed_count ?? 0;
              const totalCap = salesModal.data?.summary?.capacity ?? '∞';
              const revenue = salesModal.data?.summary?.confirmed_cash ?? 0;
              return (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{totalSold}</div><div className="text-[10px] text-muted-foreground">{msg('FE_EVENT_CONFIRMED_TICKETS', 'Confirmed tickets')}</div></div>
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{totalCap}</div><div className="text-[10px] text-muted-foreground">Total Capacity</div></div>
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-primary">₦{revenue.toLocaleString()}</div><div className="text-[10px] text-muted-foreground">{msg('FE_EVENT_CONFIRMED_CASH', 'Cash on confirmed tickets')}</div></div>
                  </div>
                  <div className="space-y-2">
                    {tiers.map((t) => (
                      <div key={t.id} className="rounded-xl bg-card border border-border p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-bold text-sm text-foreground">{t.name}</span>
                          <Pill tone={(t.confirmed_count || 0) >= (t.quantity_available || t.capacity || t.available || 0) ? 'red' : 'green'}>{t.confirmed_count || 0}/{t.quantity_available || t.capacity || t.available || 0} sold</Pill>
                        </div>
                        <div className="text-xs text-muted-foreground">₦{t.price_wallet || t.price_naira || 0} · {t.price_hp || 0} HP</div>
                        <div className="mt-1.5 h-1.5 rounded-full bg-secondary overflow-hidden">
                          <div className="h-full bg-gradient-cta" style={{ width: `${Math.min(100, ((t.confirmed_count || 0) / (t.quantity_available || t.capacity || t.available || 1)) * 100)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        )}
      </Modal>

      <Modal open={!!emailModal} onClose={() => setEmailModal(null)} title="Send Registrant List to Host">
        {emailModal && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">The full registrant list (names, ticket IDs, tiers, check-in status) will be emailed to the host so they can manage entry at the venue.</p>
            <Field label="Host Email"><TextInput type="email" value={emailModal.email} onChange={(e) => setEmailModal({ ...emailModal, email: e.target.value })} placeholder="host@example.com" /></Field>
            <button onClick={() => emailToHost(emailModal.eventId, emailModal.email)} disabled={!emailModal.email || sendingEmail} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2">
              {sendingEmail ? <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Sending...</> : 'Send Registrant List'}
            </button>
          </div>
        )}
      </Modal>

      <Modal open={!!qr} onClose={() => setQr(null)} title="Event Check-in QR">
        {qr && (
          <div className="text-center space-y-3">
            {qr.qr_image && <><img src={qr.qr_image} alt={msg('FE_EVENT_VENUE_QR', 'Venue check-in QR code')} className="w-64 h-64 mx-auto object-contain bg-white" /><a href={qr.qr_image} download={`event-${qr.event_id}-venue-qr.png`} className="font-bold text-primary">{msg('FE_EVENT_DOWNLOAD_QR', 'Download venue QR')}</a></>}
            <div className="p-4 rounded-xl bg-foreground/90 text-primary/60 font-mono text-sm break-all">{qr.qr_payload}</div>
            <p className="text-xs text-muted-foreground">Display this QR at the venue. Attendees scan it to check in and claim HP.</p>
          </div>
        )}
      </Modal>

      {scannerEvent && <EventCheckInScanner eventId={scannerEvent} onScan={token => { const id = scannerEvent; setScannerEvent(null); void admitTicket(id,token); }} onClose={() => setScannerEvent(null)} />}
      {tiersModal && (tiersModal.loading || tiersModal.error) && <Modal open onClose={() => {panelLoad.current++;setTiersModal(null);}} title="Ticket Tiers"><p role={tiersModal.error ? 'alert' : 'status'}>{tiersModal.error ? msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.") : msg('FE_EVENT_LOADING', 'Loading event details…')}</p>{tiersModal.error && <button onClick={() => viewTiers(tiersModal.eventId)}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button>}</Modal>}
      {tiersModal && !tiersModal.loading && !tiersModal.error && <TicketTiersModal eventId={tiersModal.eventId} initialTiers={tiersModal.tiers} onClose={() => {panelLoad.current++;setTiersModal(null);}} />}
    </div>
  );
}

function TicketTiersModal({ eventId, initialTiers, onClose }) {
  const tierWriting = useRef(false);
  const [tiers, setTiers] = useState(initialTiers || []);
  const [adding, setAdding] = useState(false);
  const [editTier, setEditTier] = useState(null);
  const [newTier, setNewTier] = useState<{ name: string; price_wallet: number | string; price_hp: number | string; price_full: number | string; quantity_available: number | string; description: string }>({ name: '', price_wallet: 0, price_hp: 0, price_full: '', quantity_available: 50, description: '' });
  const [busy, setBusy] = useState(null);

  const addTier = async () => {
    if (tierWriting.current) return;
    tierWriting.current = true; setBusy('add');
    try {
      const body = { name: newTier.name, price_naira: Number(newTier.price_wallet), price_naira_full: newTier.price_full === '' ? null : Number(newTier.price_full), price_hp: Number(newTier.price_hp), capacity: newTier.quantity_available === '' ? null : Number(newTier.quantity_available), description: newTier.description };
      const created = await mockApi.admin.createEventTicketTier(eventId, body);
      setTiers([...tiers, created]);
      setNewTier({ name: '', price_wallet: 0, price_hp: 0, price_full: '', quantity_available: 50, description: '' });
      setAdding(false);
      toast({ title: msg('FE_ADMIN_EVENTS_TIER_ADDED', '✅ Tier added'), description: `"${body.name}" tier created.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    tierWriting.current = false; setBusy(null);
  };

  const saveEditTier = async () => {
    if (tierWriting.current) return;
    tierWriting.current = true; setBusy(editTier.id);
    try {
      const body = { name: editTier.name, price_naira: Number(editTier.price_wallet), price_naira_full: editTier.price_full === '' ? null : Number(editTier.price_full), price_hp: Number(editTier.price_hp), capacity: editTier.quantity_available === '' ? null : Number(editTier.quantity_available), description: editTier.description || '' };
      const updated = await mockApi.admin.updateEventTicketTier(eventId, editTier.id, body);
      setTiers(tiers.map(t => t.id === editTier.id ? (updated || { ...t, ...body }) : t));
      setEditTier(null);
      toast({ title: msg('FE_ADMIN_EVENTS_TIER_UPDATED', '✅ Tier updated'), description: `"${body.name}" saved.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    tierWriting.current = false; setBusy(null);
  };

  const deleteTier = async (tierId, name) => {
    if (!(await confirmAction({ title: `Delete "${name}" tier?`, destructive: true }))) return;
    if (tierWriting.current) return;
    tierWriting.current = true; setBusy(tierId);
    try { await mockApi.admin.deleteEventTicketTier(eventId, tierId); setTiers(tiers.filter(t => t.id !== tierId)); toast({ title: msg('FE_ADMIN_EVENTS_TIER_DELETED', 'Tier deleted'), description: `"${name}" removed.` }); }
    catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    tierWriting.current = false; setBusy(null);
  };

  const toggleTier = async (tier) => {
    if (tierWriting.current) return;
    tierWriting.current = true; setBusy(tier.id);
    try { const result = await mockApi.admin.updateEventTicketTier(eventId,tier.id,{is_active: tier.is_active === false}); setTiers(rows => rows.map(row => row.id === tier.id ? {...row,...result} : row)); }
    catch (e) { toast({title:msg('FE_ADMIN_EVENTS_FAILED','Failed'),description:e.message,variant:'destructive'}); }
    finally {tierWriting.current = false;setBusy(null);}
  };

  return (
    <Modal open onClose={onClose} title="Ticket Tiers">
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">Add multiple ticket sizes under this event (e.g. Regular, VIP, Early Bird, Group). Each tier tracks its own stock and sales.</p>
        {tiers.map((t) => (
          <div key={t.id} className="rounded-xl bg-muted border border-border p-3">
            {editTier?.id === t.id ? (
              <div className="space-y-2">
                <Field label="Tier Name"><TextInput value={editTier.name} onChange={(e) => setEditTier({ ...editTier, name: e.target.value })} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Wallet Price (₦)"><TextInput type="number" value={editTier.price_wallet} onChange={(e) => setEditTier({ ...editTier, price_wallet: e.target.value })} /></Field>
                  <Field label="HP Price"><TextInput type="number" value={editTier.price_hp} onChange={(e) => setEditTier({ ...editTier, price_hp: e.target.value })} /></Field>
                </div>
                <Field label={msg('FE_TIER_FACE_PRICE', 'Full ticket price (₦)')}><TextInput type="number" value={editTier.price_full} onChange={(e) => setEditTier({ ...editTier, price_full: e.target.value })} /></Field>
                <Field label="Description"><TextInput value={editTier.description || ''} onChange={(e) => setEditTier({ ...editTier, description: e.target.value })} /></Field>
                <Field label="Quantity Available"><TextInput type="number" value={editTier.quantity_available} onChange={(e) => setEditTier({ ...editTier, quantity_available: e.target.value })} /></Field>
                <div className="flex gap-2">
                  <button onClick={saveEditTier} disabled={busy === t.id} className="flex-1 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">Save</button>
                  <button onClick={() => setEditTier(null)} className="px-4 py-2 rounded-full bg-secondary text-muted-foreground text-xs font-bold">Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-sm text-foreground">{t.name}</span>
                    <Toggle label={msg('FE_EVENT_TIER_ACTIVE', 'Sell {tier} tickets', {tier:t.name})} checked={t.is_active !== false} disabled={!!busy} onChange={() => void toggleTier(t)} />
                  <div className="flex gap-1">
                    <button onClick={() => setEditTier({ ...t, price_wallet: t.price_naira ?? 0, price_full: t.price_naira_full ?? '', quantity_available: t.capacity ?? '' })} className="p-1 rounded-lg hover:bg-secondary"><Pencil className="w-3.5 h-3.5 text-muted-foreground" /></button>
                    <button onClick={() => deleteTier(t.id, t.name)} disabled={busy === t.id} className="p-1 rounded-lg hover:tone-error"><Trash2 className="w-3.5 h-3.5 text-destructive" /></button>
                  </div>
                </div>
                <div className="text-xs text-muted-foreground">₦{t.price_wallet || t.price_naira || 0} · {t.price_hp || 0} HP · {t.quantity_sold || t.tickets_sold || t.sold_count || 0}/{t.quantity_available || t.capacity || t.available || 0} sold</div>
                {t.description && <div className="text-xs text-muted-foreground mt-1">{t.description}</div>}
                <div className="mt-1.5 h-1.5 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full bg-gradient-cta" style={{ width: `${Math.min(100, ((t.quantity_sold || t.tickets_sold || t.sold_count || 0) / (t.quantity_available || t.capacity || t.available || 1)) * 100)}%` }} />
                </div>
              </>
            )}
          </div>
        ))}
        {adding ? (
          <div className="rounded-xl bg-primary/10 border border-primary/20 p-3 space-y-2">
            <Field label="Tier Name"><TextInput value={newTier.name} onChange={(e) => setNewTier({ ...newTier, name: e.target.value })} placeholder="Regular / VIP / Early Bird / Group" /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Wallet Price (₦)"><TextInput type="number" value={newTier.price_wallet} onChange={(e) => setNewTier({ ...newTier, price_wallet: e.target.value })} /></Field>
              <Field label="HP Price"><TextInput type="number" value={newTier.price_hp} onChange={(e) => setNewTier({ ...newTier, price_hp: e.target.value })} /></Field>
            </div>
            <Field label={msg('FE_TIER_FACE_PRICE', 'Full ticket price (₦)')}><TextInput type="number" value={newTier.price_full} onChange={(e) => setNewTier({ ...newTier, price_full: e.target.value })} /></Field>
                <Field label="Description"><TextInput value={newTier.description || ''} onChange={(e) => setNewTier({ ...newTier, description: e.target.value })} /></Field>
                <Field label="Quantity Available"><TextInput type="number" value={newTier.quantity_available} onChange={(e) => setNewTier({ ...newTier, quantity_available: e.target.value })} /></Field>
            <div className="flex gap-2">
              <button onClick={addTier} disabled={!newTier.name || busy === 'add'} className="flex-1 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">Add Tier</button>
              <button onClick={() => setAdding(false)} className="px-4 py-2 rounded-full bg-secondary text-muted-foreground text-xs font-bold">Cancel</button>
            </div>
          </div>
        ) : (
          <button onClick={() => setAdding(true)} className="flex items-center gap-1 w-full py-2.5 rounded-full border-2 border-dashed border-border text-muted-foreground text-xs font-bold"><Plus className="w-4 h-4" /> Add Ticket Tier</button>
        )}
      </div>
    </Modal>
  );
}
