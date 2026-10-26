import { confirmAction } from '@/lib/confirmAction';
import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, Eye, QrCode, Ticket, Download, Mail, BarChart3 } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { safeText } from '@/lib/valueText';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill, Toggle } from './AdminShared';
import ImageUploader from './ImageUploader';
import { msg } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';

const BLANK = { title: '', description: '', location: '', starts_at: '', ends_at: '', hp_reward: 30, hp_per_attendee: 30, max_attendees: 100, funding_source: 'hg_funded', is_paid: false, is_featured: false, image_url: '' };

export default function AdminEvents() {
  const { user } = useHolyGrill();
  const canManage = (event) => user?.role === 'super_admin' || !!event.campus_id;
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [regs, setRegs] = useState(null);
  const [qr, setQr] = useState(null);
  const [tiersModal, setTiersModal] = useState(null);
  const [salesModal, setSalesModal] = useState(null);
  const [emailModal, setEmailModal] = useState(null);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const load = async () => { setLoading(true); setLoadError(false); try { setEvents(await mockApi.admin.getEvents()); } catch { setLoadError(true); } finally { setLoading(false); } };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy('save');
    const body = { ...modal.item, hp_reward: Number(modal.item.hp_reward), hp_per_attendee: Number(modal.item.hp_reward), max_attendees: Number(modal.item.max_attendees), capacity: Number(modal.item.max_attendees), is_featured: !!modal.item.is_featured, is_paid: !!modal.item.is_paid };
    try {
      let savedEvent = null;
      if (modal.isNew) { savedEvent = await mockApi.admin.createEvent(body); toast({ title: msg('FE_ADMIN_EVENTS_EVENT_CREATED', '✅ Event created'), description: msg('FE_ADMIN_EVENTS_TITLE_IS_NOW_LIVE', '"{title}" is now live.', { title: body.title }) }); }
      else { await mockApi.admin.updateEvent(modal.item.id, body); savedEvent = { id: modal.item.id }; toast({ title: msg('FE_ADMIN_EVENTS_EVENT_UPDATED', '✅ Event updated'), description: msg('FE_ADMIN_EVENTS_TITLE_HAS_BEEN_SAVED', '"{title}" has been saved.', { title: body.title }) }); }
      setModal(null); await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED_TO_SAVE', 'Failed to save'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const togglePub = async (id) => {
    try { await mockApi.admin.toggleEventPublish(id); toast({ title: msg('FE_ADMIN_EVENTS_PUBLISH_STATUS_TOGGLED', 'Publish status toggled') }); await load(); }
    catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  const remove = async (id) => {
    if (await confirmAction({ title: "Delete event?", destructive: true, confirmLabel: "Delete" })) {
      try { await mockApi.admin.deleteEvent(id); toast({ title: msg('FE_ADMIN_EVENTS_EVENT_DELETED', 'Event deleted') }); await load(); }
      catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    }
  };

  const viewRegs = async (id) => {
    try { setRegs({ eventId: id, data: await mockApi.admin.getEventRegistrants(id), tierFilter: '', checkinFilter: '' }); }
    catch (e) { setRegs({ eventId: id, data: [], tierFilter: '', checkinFilter: '' }); }
  };

  const genQR = async (id) => {
    try { setQr(await mockApi.admin.generateEventQR(id)); toast({ title: msg('FE_ADMIN_EVENTS_QR_CODE_GENERATED', 'QR code generated') }); }
    catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  const viewTiers = async (id) => {
    try { setTiersModal({ eventId: id, tiers: await mockApi.admin.getEventTicketTiers(id) }); }
    catch (e) { setTiersModal({ eventId: id, tiers: [] }); }
  };

  const viewSales = async (id) => {
    try { setSalesModal({ eventId: id, data: await mockApi.admin.getEventTicketSales(id) }); }
    catch (e) { setSalesModal({ eventId: id, data: null }); }
  };

  const exportRegs = async (eventId) => {
    setBusy('export');
    try {
      // TODO(ts): the export endpoint's envelope varies (rows/data/registrants/array).
       
      const res: any = await mockApi.admin.exportEventRegistrations(eventId);
      const rows = res?.rows || res?.data || res?.registrants || (Array.isArray(res) ? res : []);
      if (!rows.length) { toast({ title: msg('FE_ADMIN_EVENTS_NO_REGISTRANTS_TO_EXPORT', 'No registrants to export'), description: msg('FE_ADMIN_EVENTS_THE_EXPORT_ENDPOINT_RETURNED_NO_DATA', 'The export endpoint returned no data.'), variant: 'destructive' }); return; }
      const headers = Object.keys(rows[0]);
      const csv = [headers.join(','), ...rows.map(r => headers.map(h => `"${String(r[h] ?? '').replace(/"/g, '""')}"`).join(','))].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `event_${eventId}_registrations.csv`; a.click();
      URL.revokeObjectURL(url);
      toast({ title: msg('FE_ADMIN_EVENTS_CSV_EXPORTED', '✅ CSV exported'), description: `${rows.length} registrants downloaded.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_EXPORT_FAILED', 'Export failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
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
      {events.map((e) => (
        <div key={e.id} className="rounded-2xl bg-card border border-border p-3 flex items-center gap-2 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-sm text-foreground">{e.title}</span>
              {e.is_published ? <Pill tone="green">Published</Pill> : <Pill tone="amber">Draft</Pill>}
              {e.is_featured && <Pill tone="flame">Featured</Pill>}
              {e.is_paid && <Pill tone="blue">Paid</Pill>}
            </div>
            <div className="text-xs text-muted-foreground">{e.location} · {e.checkin_count}/{e.max_attendees} checked in · {e.hp_reward ?? e.hp_per_attendee} HP</div>
          </div>
          {canManage(e) && <Toggle checked={e.is_published} onChange={() => togglePub(e.id)} />}
          <button disabled={!canManage(e)} onClick={() => viewTiers(e.id)} title="Ticket Tiers" className="p-2 rounded-lg hover:bg-muted"><Ticket className="w-4 h-4 text-purple-500" /></button>
          <button onClick={() => viewSales(e.id)} title="Sales Dashboard" className="p-2 rounded-lg hover:bg-muted"><BarChart3 className="w-4 h-4 text-success" /></button>
          <button disabled={!canManage(e)} onClick={() => viewRegs(e.id)} title="Registrants" className="p-2 rounded-lg hover:bg-muted"><Eye className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => genQR(e.id)} title="QR" className="p-2 rounded-lg hover:bg-muted"><QrCode className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => setModal({ item: { ...e }, isNew: false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
          <button disabled={!canManage(e)} onClick={() => remove(e.id)} className="p-2 rounded-lg hover:tone-error"><Trash2 className="w-4 h-4 text-destructive" /></button>
        </div>
      ))}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.isNew ? 'New Event' : 'Edit Event'}>
        {modal && (
          <div className="space-y-3">
            <Field label="Title"><TextInput value={modal.item.title} onChange={(e) => setModal({ item: { ...modal.item, title: e.target.value }, isNew: modal.isNew })} /></Field>
            <Field label="Description"><textarea value={modal.item.description} onChange={(e) => setModal({ item: { ...modal.item, description: e.target.value }, isNew: modal.isNew })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
            <Field label="Location"><TextInput value={modal.item.location} onChange={(e) => setModal({ item: { ...modal.item, location: e.target.value }, isNew: modal.isNew })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Starts"><TextInput type="datetime-local" value={modal.item.starts_at} onChange={(e) => setModal({ item: { ...modal.item, starts_at: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label="Ends"><TextInput type="datetime-local" value={modal.item.ends_at} onChange={(e) => setModal({ item: { ...modal.item, ends_at: e.target.value }, isNew: modal.isNew })} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="HP Reward (per attendee)"><TextInput type="number" value={modal.item.hp_reward} onChange={(e) => setModal({ item: { ...modal.item, hp_reward: e.target.value }, isNew: modal.isNew })} /></Field>
              <Field label="Max attendees"><TextInput type="number" value={modal.item.max_attendees} onChange={(e) => setModal({ item: { ...modal.item, max_attendees: e.target.value }, isNew: modal.isNew })} /></Field>
            </div>
            <Field label="Funding Source">
              <select value={modal.item.funding_source} onChange={(e) => setModal({ item: { ...modal.item, funding_source: e.target.value }, isNew: modal.isNew })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                <option value="hg_funded">HG Funded</option>
                <option value="host_funded">Host Funded</option>
              </select>
            </Field>
            <p className="text-xs text-muted-foreground">{msg('FE_EVENT_PRICING_TIERS', 'Set ticket prices and HP discounts in Ticket Tiers after saving the event.')}</p>
            <Field label="Image"><ImageUploader value={modal.item.image_url} onChange={(url) => setModal({ item: { ...modal.item, image_url: url }, isNew: modal.isNew })} folder="events" /></Field>
            <div className="flex items-center gap-4">
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

      <Modal open={!!regs} onClose={() => setRegs(null)} title="Event Registrants">
        {regs && (
          <div className="space-y-3">
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
                <div key={r.id} className="flex items-center justify-between p-2.5 rounded-lg bg-muted text-sm">
                  <div className="min-w-0">
                    <div className="font-bold text-foreground">{r.full_name || r.name || 'Attendee'}</div>
                    <div className="text-xs text-muted-foreground truncate">{r.email || '—'} · {r.ticket_id || '—'}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {safeText(r.tier_name || r.tier, '') && <Pill tone="blue">{safeText(r.tier_name || r.tier, '')}</Pill>}
                    {r.checked_in ? <Pill tone="green">✓ Checked in</Pill> : <Pill tone="cocoa">Registered</Pill>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!salesModal} onClose={() => setSalesModal(null)} title="Ticket Sales Dashboard">
        {salesModal && (
          <div className="space-y-3">
            {(() => {
              const tiers = salesModal.data?.tiers || salesModal.data?.sales || [];
              if (!tiers.length) return <p className="text-xs text-muted-foreground text-center py-4">No sales data available yet. Add ticket tiers to start selling.</p>;
              const totalSold = tiers.reduce((s, t) => s + (t.quantity_sold || t.tickets_sold || t.sold_count || 0), 0);
              const totalCap = tiers.reduce((s, t) => s + (t.quantity_available || t.capacity || t.available || 0), 0);
              const revenue = tiers.reduce((s, t) => s + (t.quantity_sold || t.tickets_sold || t.sold_count || 0) * (t.price_wallet || t.price_naira || 0), 0);
              return (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{totalSold}</div><div className="text-[10px] text-muted-foreground">Total Sold</div></div>
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-foreground">{totalCap}</div><div className="text-[10px] text-muted-foreground">Total Capacity</div></div>
                    <div className="rounded-xl bg-muted p-3 text-center"><div className="font-heading font-extrabold text-lg text-primary">₦{revenue.toLocaleString()}</div><div className="text-[10px] text-muted-foreground">Revenue</div></div>
                  </div>
                  <div className="space-y-2">
                    {tiers.map((t) => (
                      <div key={t.id} className="rounded-xl bg-card border border-border p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-bold text-sm text-foreground">{t.name}</span>
                          <Pill tone={(t.quantity_sold || t.tickets_sold || t.sold_count || 0) >= (t.quantity_available || t.capacity || t.available || 0) ? 'red' : 'green'}>{t.quantity_sold || t.tickets_sold || t.sold_count || 0}/{t.quantity_available || t.capacity || t.available || 0} sold</Pill>
                        </div>
                        <div className="text-xs text-muted-foreground">₦{t.price_wallet || t.price_naira || 0} · {t.price_hp || 0} HP</div>
                        <div className="mt-1.5 h-1.5 rounded-full bg-secondary overflow-hidden">
                          <div className="h-full bg-gradient-cta" style={{ width: `${Math.min(100, ((t.quantity_sold || t.tickets_sold || t.sold_count || 0) / (t.quantity_available || t.capacity || t.available || 1)) * 100)}%` }} />
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
            <div className="p-4 rounded-xl bg-foreground/90 text-primary/60 font-mono text-sm break-all">{qr.qr_payload}</div>
            <p className="text-xs text-muted-foreground">Display this QR at the venue. Attendees scan it to check in and claim HP.</p>
          </div>
        )}
      </Modal>

      {tiersModal && <TicketTiersModal eventId={tiersModal.eventId} initialTiers={tiersModal.tiers} onClose={() => setTiersModal(null)} />}
    </div>
  );
}

function TicketTiersModal({ eventId, initialTiers, onClose }) {
  const [tiers, setTiers] = useState(initialTiers || []);
  const [adding, setAdding] = useState(false);
  const [editTier, setEditTier] = useState(null);
  const [newTier, setNewTier] = useState<{ name: string; price_wallet: number | string; price_hp: number | string; price_full: number | string; quantity_available: number | string; description: string }>({ name: '', price_wallet: 0, price_hp: 0, price_full: '', quantity_available: 50, description: '' });
  const [busy, setBusy] = useState(null);

  const addTier = async () => {
    setBusy('add');
    try {
      const body = { name: newTier.name, price_naira: Number(newTier.price_wallet), price_naira_full: newTier.price_full === '' ? null : Number(newTier.price_full), price_hp: Number(newTier.price_hp), capacity: newTier.quantity_available === '' ? null : Number(newTier.quantity_available), description: newTier.description };
      const created = await mockApi.admin.createEventTicketTier(eventId, body);
      setTiers([...tiers, created]);
      setNewTier({ name: '', price_wallet: 0, price_hp: 0, price_full: '', quantity_available: 50, description: '' });
      setAdding(false);
      toast({ title: msg('FE_ADMIN_EVENTS_TIER_ADDED', '✅ Tier added'), description: `"${body.name}" tier created.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const saveEditTier = async () => {
    setBusy(editTier.id);
    try {
      const body = { name: editTier.name, price_naira: Number(editTier.price_wallet), price_naira_full: editTier.price_full === '' ? null : Number(editTier.price_full), price_hp: Number(editTier.price_hp), capacity: editTier.quantity_available === '' ? null : Number(editTier.quantity_available), description: editTier.description || '' };
      const updated = await mockApi.admin.updateEventTicketTier(eventId, editTier.id, body);
      setTiers(tiers.map(t => t.id === editTier.id ? (updated || { ...t, ...body }) : t));
      setEditTier(null);
      toast({ title: msg('FE_ADMIN_EVENTS_TIER_UPDATED', '✅ Tier updated'), description: `"${body.name}" saved.` });
    } catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const deleteTier = async (tierId, name) => {
    if (!(await confirmAction({ title: `Delete "${name}" tier?`, destructive: true }))) return;
    setBusy(tierId);
    try { await mockApi.admin.deleteEventTicketTier(eventId, tierId); setTiers(tiers.filter(t => t.id !== tierId)); toast({ title: msg('FE_ADMIN_EVENTS_TIER_DELETED', 'Tier deleted'), description: `"${name}" removed.` }); }
    catch (e) { toast({ title: msg('FE_ADMIN_EVENTS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
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
