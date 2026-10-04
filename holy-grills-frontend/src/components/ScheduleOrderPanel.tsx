import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import type { DeliveryWindow, DeliveryWindowsStatus } from '@/types/orders';

// Backend times are West Africa Time — anchor to UTC+1 so the window shown is
// the same one the backend will place the order in, on any device timezone.
const watDate = (date, time) => (date && time ? new Date(`${date}T${time.length === 5 ? time + ':00' : time}+01:00`) : null);

/**
 * ScheduleOrderPanel — the "next ordering window" step, shared by the
 * closed-store popup (home) and the kitchen radar's schedule sheet (menu).
 *
 * There is no date picker: the backend's next bookable window is auto-selected
 * and remembered for checkout (sessionStorage hg_scheduled_window), which is
 * what Checkout reads to pre-apply the delivery window.
 */
export default function ScheduleOrderPanel({
  status,
  windows = [],
  onBack,
  onConfirm,
  showBack = true,
}: {
  status?: DeliveryWindowsStatus | null;
  windows?: DeliveryWindow[];
  /** Only needed when `showBack` is true. */
  onBack?: () => void;
  onConfirm?: () => void;
  showBack?: boolean;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const opensAt = watDate(status?.next_available_date, status?.next_opens_at);
  const nextWindow = windows.find((w) => w && !w.is_closed && !w.is_full) || windows[0] || null;

  const confirm = () => {
    if (nextWindow) {
      try { sessionStorage.setItem('hg_scheduled_window', JSON.stringify(nextWindow)); } catch { /* ignore */ }
    }
    onConfirm?.();
    if (pathname !== '/menu') navigate('/menu');
  };

  return (
    <>
      <h2 className="font-heading font-extrabold text-lg text-foreground text-center">Schedule your order</h2>
      <p className="text-sm text-muted-foreground text-center mt-1.5 leading-relaxed">
        No date to pick — we'll place it in the next ordering window automatically.
      </p>

      {opensAt && (
        <div className="mt-4 rounded-2xl border border-border bg-secondary/40 px-4 py-3 text-center">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Next window</p>
          <p className="font-heading font-bold text-sm text-foreground mt-0.5">
            {opensAt.toLocaleDateString('en-NG', { weekday: 'long', day: 'numeric', month: 'short' })}
          </p>
        </div>
      )}

      <div className="mt-6 flex gap-2">
        {showBack && (
          <button onClick={onBack} className="flex-1 py-3 rounded-full border border-border text-muted-foreground font-semibold text-sm hover:bg-secondary transition">
            Back
          </button>
        )}
        <button onClick={confirm} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm hg-press">
          Continue
        </button>
      </div>
    </>
  );
}