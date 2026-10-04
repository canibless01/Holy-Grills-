import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, Check, Ticket, ChevronRight, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatDateTime } from '@/lib/hgUtils';
import MascotStandee from '@/components/mascot/MascotStandee';

// Student "My Events" — the tickets this user has registered for, split into
// upcoming / checked-in / past. Backed by GET /events/my-tickets. Event titles
// are not guaranteed on the ticket rows, so we enrich from the public events
// list when it's available.
const STATUS_TONE = {
  confirmed: 'bg-success/15 text-success',
  pending: 'bg-accent/15 text-primary',
  cancelled: 'bg-destructive/15 text-destructive',
  attended: 'bg-success/15 text-success',
};

export default function MyEvents() {
  const navigate = useNavigate();
  const { isAuthenticated } = useHolyGrill();
  const [data, setData] = useState(null);
  const [eventMap, setEventMap] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [tickets, eventsRes] = await Promise.all([
          liveApi.events.myTickets().catch(() => null),
          liveApi.events.list().catch(() => null),
        ]);
        const all = Array.isArray(eventsRes) ? eventsRes : (eventsRes?.events || eventsRes?.data || []);
        const map = {};
        (all || []).forEach((e) => { map[e.id] = e; });
        setEventMap(map);
        setData(tickets || { upcoming: [], checked_in: [], past: [] });
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="text-center py-12">
        <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-3" alt="Sign in to see your events" />
        <p className="text-sm font-semibold text-foreground">Sign in to see your events</p>
        <button onClick={() => navigate('/login')} className="mt-3 text-sm font-bold text-primary">Log in →</button>
      </div>
    );
  }

  const upcoming = data?.upcoming || [];
  const checkedIn = data?.checked_in || [];
  const past = data?.past || [];
  const all = [...upcoming, ...checkedIn, ...past];

  if (!all.length) {
    return (
      <div className="text-center py-12">
        <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-3" alt="No tickets yet" />
        <p className="text-sm font-semibold text-foreground">No tickets yet</p>
        <p className="text-xs text-muted-foreground mt-1">Browse events and grab a ticket to see it here.</p>
        <button onClick={() => navigate('/events')} className="mt-3 text-sm font-bold text-primary">Browse events →</button>
      </div>
    );
  }

  const renderTicket = (t) => {
    const evt = eventMap[t.event_id] || {};
    const title = evt.title || t.event_title || t.title || 'Your event';
    const when = t.starts_at || evt.starts_at;
    const location = evt.location || t.location;
    const hp = evt.hp_per_attendee ?? evt.hp_reward ?? t.hp_reward ?? 0;
    return (
      <button
        key={`${t.event_id}-${t.ticket_id}`}
        onClick={() => navigate(`/events/${t.event_id}`)}
        className="w-full text-left rounded-2xl bg-card border border-border p-3.5 flex items-center gap-3 hover:shadow-card transition-all active:scale-[0.99]"
      >
        <div className="w-11 h-11 rounded-xl bg-gradient-cta/10 flex items-center justify-center shrink-0">
          {t.checked_in ? <Check className="w-5 h-5 text-success" /> : <Ticket className="w-5 h-5 text-primary" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-sm text-foreground truncate">{title}</div>
          <div className="text-xs text-muted-foreground truncate flex items-center gap-1.5">
            <Calendar className="w-3 h-3 shrink-0" />
            {when ? formatDateTime(when) : 'Date TBA'}
            {location && <span className="truncate">· {location}</span>}
          </div>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {t.tier_name && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/15 text-primary">{t.tier_name}</span>}
            {t.checked_in
              ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-success/15 text-success">✓ Checked in{hp ? ` · +${hp} HP` : ''}</span>
              : <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_TONE[t.status] || 'bg-secondary text-foreground'}`}>{t.status || 'confirmed'}</span>}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
      </button>
    );
  };

  return (
    <div className="space-y-5">
      {upcoming.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-heading font-extrabold text-sm text-foreground">Upcoming</h3>
          {upcoming.map(renderTicket)}
        </div>
      )}
      {checkedIn.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-heading font-extrabold text-sm text-foreground">Checked in</h3>
          {checkedIn.map(renderTicket)}
        </div>
      )}
      {past.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-heading font-extrabold text-sm text-muted-foreground">Past</h3>
          {past.map(renderTicket)}
        </div>
      )}
    </div>
  );
}