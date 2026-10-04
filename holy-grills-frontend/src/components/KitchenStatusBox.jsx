import React, { useState, useEffect } from 'react';
import { ICONS, ICON_SIZES } from '@/config/icons';
import { liveApi } from '@/lib/liveApi';
import { computeNextOpening } from '@/lib/kitchenSchedule';
import ScheduleOrderPanel from '@/components/ScheduleOrderPanel';

const { Clock, ChevronRight, X } = ICONS;

// "18:00" → "6:00 PM"
const to12h = (t) => {
  if (!t) return '';
  const [h, m] = t.split(':').map(Number);
  if (Number.isNaN(h)) return t;
  const ampm = h >= 12 ? 'PM' : 'AM';
  const hr = h % 12 || 12;
  return `${hr}:${String(m ?? 0).padStart(2, '0')} ${ampm}`;
};

// Backend times are West Africa Time — anchor the countdown to UTC+1 so it
// stays correct even on a device set to another timezone.
const watDate = (date, time) => (date && time ? new Date(`${date}T${time.length === 5 ? time + ':00' : time}+01:00`) : null);

const countdownText = (ms) => {
  if (ms <= 0) return 'moments';
  const mins = Math.floor(ms / 60000);
  const d = Math.floor(mins / 1440);
  const h = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
};

/**
 * KitchenStatusBox — the shared live kitchen status used on the home page
 * (full box) and the menu page (compact one-line variant).
 *
 * Source of truth for open/closed is the storefront operating-hours schedule
 * (/storefront/operating-hours → is_open), NOT the delivery-windows status.
 * The delivery-windows endpoint still supplies the bookable windows + slot
 * counts shown in the open state and the scheduling options handed to the
 * closed popup. No open/close time is computed on the frontend — is_open is
 * the backend's call; only the next-opening countdown is derived here from the
 * schedule the backend already returned.
 *
 * onStatus(status): optional callback fired with the combined status so a
 * parent (the home page's KitchenClosedPopup) can reuse it.
 *
 * Refreshes on mount and every 45s; the countdown re-renders every second.
 */
export default function KitchenStatusBox({ onStatus, compact = false }) {
  const [status, setStatus] = useState(null);
  const [showSchedule, setShowSchedule] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [oh, dw] = await Promise.allSettled([
          liveApi.storefront.getOperatingHours(),
          liveApi.orders.getDeliveryWindowStatus(),
        ]);
        if (!alive) return;
        const hours = oh.status === 'fulfilled' ? oh.value : null;
        const windows = dw.status === 'fulfilled' ? dw.value : null;
        if (!hours && !windows) return;

        // Operating hours are the source of truth for open/closed.
        // is_open is null when no campus is chosen — treat as "unknown" so we
        // never falsely show a closed state to a guest who hasn't picked a campus.
        const ohIsOpen = hours?.is_open;
        const isOpen = ohIsOpen === true;
        const unknown = ohIsOpen == null;

        const allWindows = windows?.windows || [];
        const firstOpen = windows?.first_open_window
          || allWindows.find((w) => !w.is_full && !w.is_closed)
          || null;
        const nextWindow = allWindows.find((w) => !w.is_full && !w.is_closed && w.starts_at) || null;

        // When closed, the countdown target is the next operating-hours opening,
        // computed from the schedule the backend returned.
        const nextOpening = (!isOpen && !unknown && hours)
          ? computeNextOpening(hours.schedule, hours.today_override)
          : null;

        const combined = {
          // Unknown (no campus chosen / hours unreadable) must NEVER read as
          // "closed": the closed popup keys off is_open === false, so a guest who
          // hasn't picked a campus would otherwise get a permanent closed popup.
          is_open: unknown ? null : isOpen,
          unknown,
          first_open_window: isOpen ? firstOpen : null,
          next_window: nextWindow,
          windows: allWindows,
          scheduled_windows: allWindows,
          next_available_date: nextOpening?.date ?? windows?.next_available_date ?? null,
          next_opens_at: nextOpening?.time ?? windows?.next_opens_at ?? null,
          message: isOpen
            ? (firstOpen
              ? `Order now, delivery ${to12h(firstOpen.delivery_starts_at)}–${to12h(firstOpen.delivery_ends_at)}${firstOpen.remaining != null ? ` · ${firstOpen.remaining} slots left` : ''}`
              : (nextWindow ? `Kitchen is open. Next window ${nextWindow.label || ''} ${to12h(nextWindow.starts_at)}`.trim() : 'Kitchen is open'))
            : (nextOpening
              ? `Schedule your order for ${new Date(`${nextOpening.date}T00:00:00`).toLocaleDateString('en-NG', { weekday: 'long' })}`
              : 'Kitchen is currently closed. Check back soon.'),
        };
        setStatus(combined);
        onStatus?.(combined);
      } catch { /* ignore */ }
    };
    load();
    const poll = setInterval(load, 45000);
    return () => { alive = false; clearInterval(poll); };
  }, [onStatus]);

  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!status) return null;

  const { is_open: isOpen, unknown } = status;
  const firstOpen = status.first_open_window;
  const nextWindow = status.next_window;
  const opensAt = watDate(status.next_available_date, status.next_opens_at);
  const opensInMs = opensAt ? opensAt.getTime() - now : null;
  const openingSoon = !isOpen && opensInMs != null && opensInMs <= 3600000;
  // Day-level only — the exact clock time misleads (the order lands in the
  // delivery window, not at the hour the kitchen opens).
  const scheduleDay = opensAt ? opensAt.toLocaleDateString('en-NG', { weekday: 'long' }) : null;

  // Unknown (no campus yet) — render nothing rather than a false "closed".
  if (unknown) return null;

  const tone = isOpen
    ? 'border-success/25 bg-success/5 text-success'
    : (openingSoon ? 'border-success/25 bg-success/5 text-success' : 'border-destructive/25 bg-destructive/5 text-destructive');

  const scheduleModal = showSchedule ? (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => setShowSchedule(false)}>
      <div className="bg-card rounded-3xl w-full max-w-sm relative shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <button onClick={() => setShowSchedule(false)} aria-label="Close" className="absolute top-3 right-3 z-10 p-2 rounded-full bg-secondary/70 hover:bg-secondary transition-colors">
          <X size={ICON_SIZES.sm} className="text-muted-foreground" />
        </button>
        <div className="px-6 pt-8 pb-6">
          <ScheduleOrderPanel
            status={status}
            windows={status.scheduled_windows || []}
            showBack={false}
            onConfirm={() => setShowSchedule(false)}
          />
        </div>
      </div>
    </div>
  ) : null;

  // Compact variant — one line for the menu page. When closed it becomes the
  // schedule entry point, so a guest who dismissed the home popup can still
  // start a scheduled order straight from the menu.
  if (compact) {
    const body = (
      <>
        <div className="relative shrink-0">
          <div className={`w-2.5 h-2.5 rounded-full ${isOpen ? 'bg-success' : 'bg-destructive'}`} />
          {isOpen && <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-success animate-ping opacity-75" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className={`text-xs font-bold ${isOpen ? 'text-success' : 'text-destructive'}`}>{isOpen ? 'Open' : 'Closed'}</div>
          <div className="text-[11px] text-muted-foreground truncate">
            {isOpen
              ? (firstOpen
                ? `Delivery ${to12h(firstOpen.delivery_starts_at)}–${to12h(firstOpen.delivery_ends_at)}${firstOpen.remaining != null ? ` · ${firstOpen.remaining} slots left` : ''}`
                : (nextWindow ? `Next window ${to12h(nextWindow.starts_at)}` : 'Open now'))
              : (scheduleDay ? `Schedule your order for ${scheduleDay}` : 'Schedule your order for the next window')}
          </div>
        </div>
        {!isOpen && opensInMs != null && (
          <div className={`flex items-center gap-1 px-2 py-1 rounded-full border ${tone} shrink-0`}>
            <Clock size={ICON_SIZES.xs} />
            <span className="text-[10px] font-bold tabular-nums">{countdownText(opensInMs)}</span>
          </div>
        )}
        {!isOpen && <ChevronRight size={ICON_SIZES.sm} className="text-muted-foreground shrink-0" />}
      </>
    );
    const shell = 'flex items-center gap-2.5 rounded-[var(--radius-menu-card)] border border-border bg-card p-2.5 shadow-card';
    return (
      <>
        {isOpen
          ? <div className={shell}>{body}</div>
          : <button type="button" onClick={() => setShowSchedule(true)} className={`${shell} w-full text-left hg-press`}>{body}</button>}
        {scheduleModal}
      </>
    );
  }

  return (
    <>
    <div className="hg-card shadow-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className={`w-3 h-3 rounded-full ${isOpen ? 'bg-success' : 'bg-destructive'}`} />
            {isOpen && <div className="absolute inset-0 w-3 h-3 rounded-full bg-success animate-ping opacity-75" />}
          </div>
          <span className="hg-eyebrow">Kitchen Radar</span>
        </div>
        <span className={`text-xs font-bold ${isOpen ? 'text-success' : 'text-destructive'}`}>
          {isOpen ? 'Open Now' : 'Closed'}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          {isOpen ? (
            <>
              <div className="font-heading font-bold text-base text-foreground">The grill is live 🔥</div>
              <div className="text-xs text-muted-foreground mt-1">Orders are open.</div>
            </>
          ) : (
            <>
              <div className="font-heading font-bold text-base text-foreground">The grill is resting 🔥</div>
              <div className="text-xs text-muted-foreground mt-1">Next window soon.</div>
            </>
          )}
        </div>

        {!isOpen && opensInMs != null && (
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border ${tone} shrink-0`}>
            <Clock size={ICON_SIZES.xs} />
            <span className="text-xs font-bold tabular-nums">{openingSoon ? 'Opening in' : 'Opens in'} {countdownText(opensInMs)}</span>
          </div>
        )}
      </div>

      {!isOpen && (
        <button type="button" onClick={() => setShowSchedule(true)} className="w-full mt-3 py-2.5 rounded-full bg-gradient-cta text-white font-bold text-xs shadow-glow hg-press">
          Schedule my order
        </button>
      )}
    </div>
    {scheduleModal}
    </>
  );
}