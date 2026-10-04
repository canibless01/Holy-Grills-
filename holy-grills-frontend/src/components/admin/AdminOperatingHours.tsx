import { useState, useEffect } from 'react';
import { Save, Clock, CalendarOff, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Card, Field, TextInput, Toggle, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import LoadingSpinner from '@/components/LoadingSpinner';
import { msg } from '@/lib/messages';

// Admin manager for the storefront operating-hours routes (storefront.py):
//   GET   /storefront/operating-hours        → { schedule, today_override, is_open }
//   PATCH /storefront/operating-hours        { day, open_time, close_time, is_closed }
//   POST  /storefront/operating-hours/override { override_date, is_closed, open_time, close_time, reason }
// The schedule rows use `weekday` (0=Mon…6=Sun) with opens_at/closes_at columns;
// the PATCH route accepts the friendlier open_time/close_time names and maps them.
const DAYS = [
  { key: 'monday', idx: 0, label: 'Monday' },
  { key: 'tuesday', idx: 1, label: 'Tuesday' },
  { key: 'wednesday', idx: 2, label: 'Wednesday' },
  { key: 'thursday', idx: 3, label: 'Thursday' },
  { key: 'friday', idx: 4, label: 'Friday' },
  { key: 'saturday', idx: 5, label: 'Saturday' },
  { key: 'sunday', idx: 6, label: 'Sunday' },
];

const rowToForm = (r) => ({
  is_closed: !!r?.is_closed,
  open_time: r?.opens_at || r?.open_time || '08:00',
  close_time: r?.closes_at || r?.close_time || '21:00',
});

export default function AdminOperatingHours() {
  const [schedule, setSchedule] = useState(null); // array indexed by weekday
  const [override, setOverride] = useState(null);
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const [loaded, setLoaded] = useState(false);

  // Override form
  const [ovDate, setOvDate] = useState('');
  const [ovClosed, setOvClosed] = useState(true);
  const [ovOpen, setOvOpen] = useState('08:00');
  const [ovClose, setOvClose] = useState('21:00');
  const [ovReason, setOvReason] = useState('');

  const load = async () => {
    try {
      const res = await liveApi.admin.getOperatingHours();
      const sched = Array.isArray(res?.schedule) ? res.schedule : [];
      // Normalize to a 7-slot array keyed by weekday for stable rendering.
      const byIdx = new Array(7).fill(null);
      sched.forEach((r) => { if (r && r.weekday != null) byIdx[r.weekday] = r; });
      setSchedule(byIdx);
      setOverride(res?.today_override || null);
      setIsOpen(!!res?.is_open);
      if (res?.today_override) {
        setOvDate(res.today_override.date || '');
        setOvClosed(res.today_override.is_closed !== false);
        setOvOpen(res.today_override.opens_at || res.today_override.open_time || '08:00');
        setOvClose(res.today_override.closes_at || res.today_override.close_time || '21:00');
        setOvReason(res.today_override.reason || '');
      }
    } catch (e) {
      setSchedule(new Array(7).fill(null));
      toast({ title: msg('FE_ADMIN_OPERATING_HOURS_COULD_NOT_LOAD_OPERATING_HOURS', 'Could not load operating hours'), description: e.message, variant: 'destructive' });
    }
    setLoaded(true);
  };
  useEffect(() => { load(); }, []);

  const patchDay = (idx, field, value) => {
    setSchedule((arr) => arr.map((r, i) => (i === idx ? { ...(r || {}), [field]: value } : r)));
  };

  const saveDay = async (dayKey) => {
    const idx = DAYS.findIndex((d) => d.key === dayKey);
    const row = schedule[idx];
    setBusy(dayKey);
    try {
      await liveApi.admin.updateOperatingHours({
        day: dayKey,
        open_time: row?.is_closed ? null : (row?.open_time || '08:00'),
        close_time: row?.is_closed ? null : (row?.close_time || '21:00'),
        is_closed: !!row?.is_closed,
      });
      toast({ title: `✅ ${dayKey} hours saved` });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_OPERATING_HOURS_SAVE_FAILED', 'Save failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const saveOverride = async () => {
    if (!ovDate) { toast({ title: msg('FE_ADMIN_OPERATING_HOURS_PICK_A_DATE', 'Pick a date'), variant: 'destructive' }); return; }
    setBusy('override');
    try {
      await liveApi.admin.setOperatingHoursOverride({
        override_date: ovDate,
        is_closed: ovClosed,
        open_time: ovClosed ? null : ovOpen,
        close_time: ovClosed ? null : ovClose,
        reason: ovReason || undefined,
      });
      toast({ title: msg('FE_ADMIN_OPERATING_HOURS_OVERRIDE_SAVED', '✅ Override saved'), description: ovClosed ? `${ovDate} marked closed.` : `${ovDate} hours updated.` });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_OPERATING_HOURS_OVERRIDE_FAILED', 'Override failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (!loaded) return <LoadingSpinner label="Loading hours…" />;
  if (!schedule) return <Card><p className="text-xs text-muted-foreground text-center py-6">Operating hours unavailable.</p></Card>;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold ${isOpen ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
          <span className={`w-2 h-2 rounded-full ${isOpen ? 'bg-emerald-500' : 'bg-red-500'} animate-pulse`} />
          {isOpen ? 'Open now' : 'Closed now'}
        </span>
        <span className="text-[11px] text-muted-foreground">Storefront schedule (Africa/Lagos). Updates apply immediately.</span>
      </div>

      <div className="space-y-2">
        {DAYS.map((d) => {
          const row = schedule[d.idx] || {};
          const form = rowToForm(row);
          const closed = row?.is_closed ?? form.is_closed;
          return (
            <Card key={d.key}>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2 w-28 shrink-0">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                  <span className="font-bold text-sm text-foreground">{d.label}</span>
                </div>
                <Toggle checked={!closed} onChange={(v) => patchDay(d.idx, 'is_closed', !v)} />
                <span className="text-[11px] text-muted-foreground w-16">{closed ? 'Closed' : 'Open'}</span>
                {!closed && (
                  <div className="flex items-center gap-2">
                    <input type="time" value={row?.open_time || form.open_time} onChange={(e) => patchDay(d.idx, 'open_time', e.target.value)} className="p-2 rounded-lg border border-border text-sm" />
                    <span className="text-xs text-muted-foreground">→</span>
                    <input type="time" value={row?.close_time || form.close_time} onChange={(e) => patchDay(d.idx, 'close_time', e.target.value)} className="p-2 rounded-lg border border-border text-sm" />
                  </div>
                )}
                <button onClick={() => saveDay(d.key)} disabled={busy === d.key} className="ml-auto flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50">
                  {busy === d.key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save
                </button>
              </div>
            </Card>
          );
        })}
      </div>

      <Card>
        <div className="flex items-center gap-2 mb-3">
          <CalendarOff className="w-4 h-4 text-primary" />
          <h3 className="font-heading font-bold text-sm text-foreground">Date override</h3>
          {override && <Pill tone="flame">Today: {override.is_closed ? 'Closed' : 'Modified'}</Pill>}
        </div>
        <p className="text-[11px] text-muted-foreground mb-3">Close the kitchen or set special hours for a specific date (e.g. public holiday). Overrides the weekly schedule for that day only.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Date"><TextInput type="date" value={ovDate} onChange={(e) => setOvDate(e.target.value)} /></Field>
          <div className="flex items-end gap-2">
            <Toggle checked={!ovClosed} onChange={(v) => setOvClosed(!v)} />
            <span className="text-xs text-muted-foreground">{ovClosed ? 'Closed all day' : 'Open with special hours'}</span>
          </div>
          {!ovClosed && (
            <>
              <Field label="Open"><TextInput type="time" value={ovOpen} onChange={(e) => setOvOpen(e.target.value)} /></Field>
              <Field label="Close"><TextInput type="time" value={ovClose} onChange={(e) => setOvClose(e.target.value)} /></Field>
            </>
          )}
          <Field label="Reason (optional)"><TextInput value={ovReason} onChange={(e) => setOvReason(e.target.value)} placeholder="Public holiday" /></Field>
        </div>
        <button onClick={saveOverride} disabled={busy === 'override'} className="mt-3 flex items-center gap-1 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold disabled:opacity-50">
          {busy === 'override' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save override
        </button>
      </Card>
    </div>
  );
}