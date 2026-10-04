import { useState, useEffect } from 'react';
import { UtensilsCrossed, RefreshCw, Search, Calendar, Users, Phone, Mail, DollarSign, StickyNote, X } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, formatDate } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';

const STATUS_FLOW = ['new', 'reviewed', 'quoted', 'accepted', 'completed', 'rejected', 'cancelled'];

const STATUS_TONE = {
  new: 'bg-blue-100 text-blue-700',
  reviewed: 'bg-amber-100 text-amber-700',
  quoted: 'bg-purple-100 text-purple-700',
  accepted: 'bg-green-100 text-green-700',
  completed: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  cancelled: 'bg-secondary text-muted-foreground',
};

/**
 * AdminCatering — manages external catering partnership requests.
 *
 * Flow: new → reviewed → quoted → accepted → completed
 *       (or → rejected / cancelled at any point)
 *
 * Admins can: filter by status, view full request details, update status,
 * add internal notes, set quoted amount, and assign to staff.
 *
 * Also includes a tab for event catering — viewing registrants for events
 * and exporting/emailing the list to the event host.
 *
 * Backend:
 *   GET    /events/catering-requests
 *   PATCH  /events/catering-requests/:id
 *   GET    /events/:id/registrants
 *   POST   /events/:id/send-registrants-to-host
 */
export default function AdminCatering() {
  const [tab, setTab] = useState('requests');
  const [requests, setRequests] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [q, setQ] = useState('');
  const [detail, setDetail] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [reqs, evs] = await Promise.allSettled([
        liveApi.admin.getCateringRequests(),
        liveApi.admin.getEvents(),
      ]);
      setRequests(reqs.status === 'fulfilled' ? reqs.value : []);
      setEvents(evs.status === 'fulfilled' ? evs.value : []);
    } catch { setRequests([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const filtered = requests.filter((r) => {
    const okStatus = statusFilter === 'all' || r.status === statusFilter;
    const name = (r.organizer_name || '').toLowerCase();
    const event = (r.event_name || '').toLowerCase();
    const okQ = !q || name.includes(q.toLowerCase()) || event.includes(q.toLowerCase());
    return okStatus && okQ;
  });

  const statusCounts = STATUS_FLOW.reduce((acc, s) => {
    acc[s] = requests.filter((r) => r.status === s).length;
    return acc;
  }, {});

  const openDetail = (r) => {
    setDetail({
      ...r,
      _status: r.status || 'new',
      _notes: r.notes || r.admin_notes || '',
      _quoted_amount: r.quoted_amount || '',
      _assigned_to: r.assigned_to || '',
    });
  };

  const saveDetail = async () => {
    if (!detail) return;
    setSaving(true);
    try {
      const body = {
        status: detail._status,
        notes: detail._notes,
        quoted_amount: detail._quoted_amount ? Number(detail._quoted_amount) : undefined,
        assigned_to: detail._assigned_to || undefined,
      };
      await liveApi.admin.updateCateringRequest(detail.id, body);
      toast({ title: '✅ Catering request updated', description: `Status: ${detail._status}` });
      setDetail(null);
      await load();
    } catch (e) {
      toast({ title: 'Update failed', description: e.message, variant: 'destructive' });
    }
    setSaving(false);
  };

  if (loading) return <LoadingSpinner label="Loading catering requests..." />;

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="flex gap-2">
        <button onClick={() => setTab('requests')} className={`px-4 py-2 rounded-xl text-sm font-bold transition-colors ${tab === 'requests' ? 'bg-primary text-white' : 'bg-white border border-border text-foreground'}`}>
          Partnership Requests
        </button>
        <button onClick={() => setTab('event-catering')} className={`px-4 py-2 rounded-xl text-sm font-bold transition-colors ${tab === 'event-catering' ? 'bg-primary text-white' : 'bg-white border border-border text-foreground'}`}>
          Event Catering
        </button>
      </div>

      {tab === 'requests' && (
        <>
          {/* Status summary chips */}
          <div className="flex gap-2 flex-wrap">
            <button onClick={() => setStatusFilter('all')} className={`px-3 py-1.5 rounded-full text-xs font-bold transition-colors ${statusFilter === 'all' ? 'bg-foreground text-white' : 'bg-white border border-border text-muted-foreground'}`}>
              All ({requests.length})
            </button>
            {STATUS_FLOW.map((s) => statusCounts[s] > 0 && (
              <button key={s} onClick={() => setStatusFilter(s)} className={`px-3 py-1.5 rounded-full text-xs font-bold transition-colors ${statusFilter === s ? 'bg-foreground text-white' : 'bg-white border border-border text-muted-foreground'}`}>
                <span className="capitalize">{s}</span> ({statusCounts[s]})
              </button>
            ))}
          </div>

          {/* Search + refresh */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-muted-foreground" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search organizer or event..." className="w-full pl-9 pr-3 py-2 rounded-xl border border-border text-sm" />
            </div>
            <button onClick={load} className="p-2 rounded-xl border border-border"><RefreshCw className="w-4 h-4 text-muted-foreground" /></button>
          </div>

          {filtered.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground">
              <UtensilsCrossed className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
              No catering requests found.
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map((r) => (
                <button key={r.id} onClick={() => openDetail(r)} className="w-full text-left rounded-2xl bg-white border border-border p-4 hover:border-primary/40 hover:shadow-glow transition-all">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-foreground truncate">{r.organizer_name}</span>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full capitalize ${STATUS_TONE[r.status] || 'bg-secondary text-muted-foreground'}`}>{r.status || 'new'}</span>
                      </div>
                      <div className="text-xs text-foreground truncate">{r.event_name}</div>
                      <div className="text-[11px] text-muted-foreground flex items-center gap-2 mt-0.5">
                        <Calendar className="w-3 h-3" /> {formatDate(r.event_date)}
                        <Users className="w-3 h-3 ml-1" /> {r.expected_guests} guests
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      {r.quoted_amount ? (
                        <div className="font-heading font-bold text-foreground">{formatNaira(r.quoted_amount)}</div>
                      ) : r.budget ? (
                        <div className="text-xs text-muted-foreground">Budget: {formatNaira(r.budget)}</div>
                      ) : null}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'event-catering' && <EventCateringTab events={events} />}

      {/* Detail modal */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-end lg:items-center justify-center bg-black/60 backdrop-blur-md p-4" onClick={() => setDetail(null)}>
          <div className="bg-white rounded-3xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-bold text-lg text-foreground">Catering Request</h3>
              <button onClick={() => setDetail(null)} className="p-2 rounded-full hover:bg-muted"><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>

            {/* Organizer info */}
            <div className="space-y-2 mb-4">
              <div className="flex items-center gap-2 text-sm"><Users className="w-4 h-4 text-muted-foreground" /><span className="font-bold text-foreground">{detail.organizer_name}</span></div>
              <div className="flex items-center gap-2 text-sm text-foreground"><Mail className="w-4 h-4 text-muted-foreground" />{detail.email}</div>
              <div className="flex items-center gap-2 text-sm text-foreground"><Phone className="w-4 h-4 text-muted-foreground" />{detail.phone}</div>
            </div>

            {/* Event info */}
            <div className="rounded-xl bg-muted p-3 space-y-1 mb-4">
              <div className="font-bold text-sm text-foreground">{detail.event_name}</div>
              <div className="text-xs text-foreground flex items-center gap-2"><Calendar className="w-3.5 h-3.5" /> {formatDate(detail.event_date)}</div>
              <div className="text-xs text-foreground flex items-center gap-2"><Users className="w-3.5 h-3.5" /> {detail.expected_guests} expected guests</div>
              {detail.budget && <div className="text-xs text-foreground flex items-center gap-2"><DollarSign className="w-3.5 h-3.5" /> Budget: {formatNaira(detail.budget)}</div>}
              {detail.notes && <div className="text-xs text-foreground flex items-start gap-2 mt-1"><StickyNote className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {detail.notes}</div>}
            </div>

            {/* Admin controls */}
            <div className="space-y-3">
              <div>
                <label className="text-xs font-bold text-foreground mb-1 block">Status</label>
                <select value={detail._status} onChange={(e) => setDetail({ ...detail, _status: e.target.value })} className="w-full p-2 rounded-xl border border-border text-sm">
                  {STATUS_FLOW.map((s) => <option key={s} value={s} className="capitalize">{s}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-bold text-foreground mb-1 block">Quoted Amount (₦)</label>
                <input type="number" value={detail._quoted_amount} onChange={(e) => setDetail({ ...detail, _quoted_amount: e.target.value })} placeholder="e.g. 200000" className="w-full p-2 rounded-xl border border-border text-sm" />
              </div>
              <div>
                <label className="text-xs font-bold text-foreground mb-1 block">Assign to staff</label>
                <input value={detail._assigned_to} onChange={(e) => setDetail({ ...detail, _assigned_to: e.target.value })} placeholder="Staff UUID or name" className="w-full p-2 rounded-xl border border-border text-sm" />
              </div>
              <div>
                <label className="text-xs font-bold text-foreground mb-1 block">Admin Notes</label>
                <textarea value={detail._notes} onChange={(e) => setDetail({ ...detail, _notes: e.target.value })} rows={3} placeholder="Internal notes..." className="w-full p-2 rounded-xl border border-border text-sm" />
              </div>
            </div>

            <button onClick={saveDetail} disabled={saving} className="w-full mt-4 py-3 rounded-full bg-primary text-white font-bold text-sm disabled:opacity-50">
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Event Catering tab — view registrants per event, export CSV, email to host */
function EventCateringTab({ events }) {
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [registrants, setRegistrants] = useState([]);
  const [loadingRegs, setLoadingRegs] = useState(false);
  const [emailing, setEmailing] = useState(false);
  const [hostEmail, setHostEmail] = useState('');

  const loadRegistrants = async (eventId) => {
    setSelectedEvent(eventId);
    setLoadingRegs(true);
    try {
      const regs = await liveApi.admin.getEventRegistrantList(eventId);
      setRegistrants(regs);
    } catch { setRegistrants([]); }
    setLoadingRegs(false);
  };

  // /events/<id>/registrants returns flat rows: { full_name, email, phone,
  // tier_name, status, checked_in, checked_in_at, ticket_id }. Read those
  // directly (no nested `user` object).
  const exportCSV = () => {
    if (!registrants.length) return;
    const headers = ['Name', 'Email', 'Phone', 'Tier', 'Check-in', 'Catering Notes'];
    const rows = registrants.map((r) => [
      r.full_name || r.user?.name || r.name || '',
      r.email || r.user?.email || '',
      r.phone || r.user?.phone || '',
      r.tier_name || r.tier || r.ticket_tier || '',
      r.checked_in ? 'Yes' : 'No',
      r.catering_notes || r.notes || '',
    ]);
    const csv = [headers, ...rows].map((row) => row.map((c) => `"${(c || '').toString().replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `event-${selectedEvent}-registrants.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  // POST /events/<id>/send-registrants-to-host REQUIRES host_email in the body.
  const emailHost = async () => {
    if (!hostEmail) return;
    setEmailing(true);
    try {
      await liveApi.admin.sendRegistrantsToHost(selectedEvent, { host_email: hostEmail });
      toast({ title: '✅ Registrant list sent to host', description: hostEmail });
      setHostEmail('');
    } catch (e) {
      toast({ title: 'Failed to send', description: e.message, variant: 'destructive' });
    }
    setEmailing(false);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs font-bold text-foreground mb-1 block">Select Event</label>
        <select value={selectedEvent || ''} onChange={(e) => loadRegistrants(e.target.value)} className="w-full p-2 rounded-xl border border-border text-sm">
          <option value="">Choose an event...</option>
          {events.map((ev) => <option key={ev.id} value={ev.id}>{ev.title}</option>)}
        </select>
      </div>

      {selectedEvent && (
        <>
          <div className="flex gap-2">
            <button onClick={exportCSV} disabled={!registrants.length || loadingRegs} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-foreground text-white text-xs font-bold disabled:opacity-50">
              <RefreshCw className="w-3.5 h-3.5" /> Export CSV
            </button>
          </div>
          <div className="flex gap-2">
            <input type="email" value={hostEmail} onChange={(e) => setHostEmail(e.target.value)} placeholder="Host email (required)" className="flex-1 p-2.5 rounded-xl border border-border text-sm" />
            <button onClick={emailHost} disabled={!registrants.length || loadingRegs || emailing || !hostEmail} className="flex items-center gap-1.5 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
              <Mail className="w-3.5 h-3.5" /> {emailing ? 'Sending…' : 'Email to Host'}
            </button>
          </div>

          {loadingRegs ? (
            <LoadingSpinner label="Loading registrants..." />
          ) : registrants.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground">
              <Users className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
              No registrants found.
            </div>
          ) : (
            <div className="space-y-2">
              {registrants.map((r, i) => (
                <div key={r.id || i} className="rounded-2xl bg-white border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-foreground">{r.full_name || r.user?.name || r.name || 'Attendee'}</span>
                        {(r.tier_name || r.tier) && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/30 text-accent-foreground/80">{r.tier_name || r.tier}</span>}
                        {r.checked_in && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-700">Checked in</span>}
                      </div>
                      <div className="text-xs text-muted-foreground">{r.email || r.user?.email || '—'}</div>
                      {r.catering_notes && <div className="text-xs text-foreground mt-1">📝 {r.catering_notes}</div>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}