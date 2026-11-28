import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { liveApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';
import type { DeliveryWindow, DeliveryWindowsStatus } from '@/types/orders';

export default function ScheduleOrderPanel({ status: _status, windows: _windows = [], onBack, onConfirm, showBack = true }: {
  status?: DeliveryWindowsStatus | null; windows?: DeliveryWindow[]; onBack?: () => void;
  onConfirm?: (window: DeliveryWindow) => void; showBack?: boolean;
}) {
  const navigate = useNavigate(); const { pathname } = useLocation(); const { campusId } = useCampus();
  const [calendar, setCalendar] = useState<any[]>([]); const [selected, setSelected] = useState<DeliveryWindow | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true; setLoading(true); setError(false); setSelected(null); setCalendar([]);
    liveApi.orders.getScheduleCalendar(campusId).then(data => {
      if (!alive) return;
      setCalendar(data.calendar || []);
      const first = (data.calendar || []).flatMap(day => day.windows || []).find(w => !w.is_closed && !w.is_full);
      setSelected(first || null);
    }).catch(() => { if (alive) setError(true); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [campusId, retry]);
  const confirm = () => {
    if (!selected) return;
    const window = { ...selected, campus_id: campusId, starts_at: `${selected.date}T${selected.opens_at || '00:00'}+01:00` };
    try { sessionStorage.setItem('hg_scheduled_window', JSON.stringify(window)); } catch { /* optional persistence */ }
    onConfirm?.(window);
    if (pathname !== '/menu' && pathname !== '/checkout') navigate('/menu');
  };
  const dateLabel = date => new Date(`${date}T12:00:00+01:00`).toLocaleDateString('en-NG', { timeZone: 'Africa/Lagos', weekday: 'short', day: 'numeric', month: 'short' });
  return <>
    <h2 className="font-heading font-extrabold text-lg text-foreground text-center">{msg('FE_SCHEDULE_TITLE', 'Choose your delivery date')}</h2>
    <p className="text-sm text-muted-foreground text-center mt-1.5">{msg('FE_SCHEDULE_DESCRIPTION', 'Choose an available date and window. Capacity is checked again when you place your order.')}</p>
    {loading ? <p role="status" className="text-center text-sm py-4">{msg('FE_SCHEDULE_LOADING', 'Checking availability…')}</p>
      : error ? <p role="alert" className="text-center text-sm py-4">{msg('FE_SCHEDULE_ERROR', 'Availability could not be loaded.')} <button type="button" className="underline" onClick={() => setRetry(v => v + 1)}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></p>
      : <div className="mt-4 max-h-64 overflow-auto space-y-2">
        {calendar.map(day => {
          const available = day.windows.filter(w => !w.is_closed && !w.is_full);
          return <div key={day.date} className="rounded-xl border border-border p-3">
            <p className="text-sm font-bold">{dateLabel(day.date)}{!available.length && <span className="ml-2 text-xs text-muted-foreground">{day.windows.some(w => w.is_full && !w.is_closed) ? msg('FE_SCHEDULE_FULL', 'Fully booked') : msg('FE_SCHEDULE_UNAVAILABLE', 'Unavailable')}</span>}</p>
            {available.map(w => <button type="button" key={w.id} aria-pressed={selected?.id === w.id && selected?.date === w.date} onClick={() => setSelected(w)} className={`mt-2 mr-2 rounded-xl border px-3 py-2 text-xs ${selected?.id === w.id && selected?.date === w.date ? 'border-primary bg-primary/10 text-primary' : 'border-border'}`}>
              {w.delivery_starts_at && w.delivery_ends_at ? `${w.delivery_starts_at}–${w.delivery_ends_at}` : `${w.opens_at}–${w.closes_at}`}
              {w.remaining != null && <span className="block">{msg('FE_SCHEDULE_REMAINING', '{count} slots remaining', { count: w.remaining })}</span>}
            </button>)}
          </div>;
        })}
        {!selected && <p className="text-sm text-center">{msg('FE_SCHEDULE_NONE', 'No bookable dates in the next 14 days. Please check again later.')}</p>}
      </div>}
    <div className="mt-5 flex gap-2">
      {showBack && <button type="button" onClick={onBack} className="flex-1 py-3 rounded-full border border-border text-sm">{msg('FE_SCHEDULE_BACK', 'Back')}</button>}
      <button type="button" onClick={confirm} disabled={!selected || loading || error} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{msg('FE_SCHEDULE_CONFIRM', 'Use this date')}</button>
    </div>
  </>;
}
