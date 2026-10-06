import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ICONS, ICON_SIZES } from '@/config/icons';
import FlameMark from '@/components/FlameMark';
import { formatNaira } from '@/lib/hgUtils';
import { msg } from '@/lib/messages';

const { X, ArrowRight, Clock, Check, AlertCircle } = ICONS;

// Backend times are West Africa Time (UTC+1) — anchor to that so the date/time
// shown is the same one the kitchen will act on, on any device timezone.
const WAT_OFFSET_MS = 60 * 60 * 1000;
const watDate = (date, time = '00:00') => {
  if (!date) return null;
  const t = time && time.length === 5 ? `${time}:00` : (time || '00:00:00');
  return new Date(`${date}T${t}+01:00`);
};
const to12h = (t) => {
  if (!t) return '';
  const [h, m] = String(t).split(':').map(Number);
  if (Number.isNaN(h)) return String(t);
  const ampm = h >= 12 ? 'PM' : 'AM';
  return `${h % 12 || 12}:${String(m ?? 0).padStart(2, '0')} ${ampm}`;
};

/**
 * CheckoutKitchenClosedPopup — the checkout half of the closed-kitchen flow.
 *
 * It exists because the kitchen status endpoint and the order gate are two
 * different calls: `is_open` comes from GET /orders/delivery-windows/status, and
 * the refusal comes from POST /orders. A race between them (or a status call
 * that never returned) used to surface as a red "Orders can only be placed
 * during operating hours" box with no way forward.
 *
 * So: one popup, shown whenever ordering is not possible right now, offering
 * exactly two choices — schedule the order for the next opening, or cancel.
 *
 * Props:
 *  status   — the delivery-windows status ({ is_open, reason, next_available_date,
 *              next_opens_at })
 *  open     — whether to show it
 *  busy     — a schedule request is in flight
 *  onSchedule — place the order with accept_next_available_date: true
 *  onClose    — dismiss
 */
export default function CheckoutKitchenClosedPopup({ status, open, busy = false, onSchedule, onClose }) {
  const [placed, setPlaced] = useState(null);

  // A new closed episode starts from the offer, not from a stale confirmation.
  useEffect(() => {
    if (open) setPlaced(null);
  }, [open]);

  const reason = status?.reason;
  const nextDate = status?.next_available_date || null;
  const nextTime = status?.next_opens_at || null;

  const body =
    reason === 'closed_today'
      ? msg('FE_CHECKOUT_KITCHEN_CLOSED_TODAY', 'The kitchen is closed for today. You can still order now and we will schedule it for the next opening.')
      : reason === 'full'
        ? msg('FE_CHECKOUT_KITCHEN_CLOSED_FULL', "Today's slots are fully booked. You can still order now and we will schedule it for the next opening.")
        : nextTime && nextDate
          ? msg('FE_CHECKOUT_KITCHEN_CLOSED_OPENS', 'The kitchen is closed. It opens at {time}. You can still order now and we will schedule it for {date}.', { time: to12h(nextTime), date: watDate(nextDate)?.toLocaleDateString('en-NG', { weekday: 'long', day: 'numeric', month: 'short' }) || nextDate })
          : msg('FE_CHECKOUT_KITCHEN_CLOSED_NO_TIME', 'The kitchen is closed. You can still order now and we will schedule it for the next opening.');

  if (!open) return null;

  // After a successful schedule the confirmation replaces the offer, so the
  // guest sees the date and delivery window the order actually landed in.
  if (placed) {
    return (
      <AnimatePresence>
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4"
        >
          <motion.div
            initial={{ scale: 0.94, y: 24 }} animate={{ scale: 1, y: 0 }}
            className="bg-card rounded-3xl w-full max-w-sm overflow-hidden relative shadow-2xl"
          >
            <button onClick={onClose} aria-label="Close" className="absolute top-3 right-3 z-10 p-2 rounded-full bg-secondary/70 hover:bg-secondary transition-colors">
              <X size={ICON_SIZES.sm} className="text-muted-foreground" />
            </button>
            <div className="px-6 pt-8 pb-6 text-center">
              <div className="w-14 h-14 rounded-2xl bg-success/15 flex items-center justify-center mx-auto mb-4">
                <Check className="w-7 h-7 text-success" />
              </div>
              <h2 className="font-heading font-extrabold text-xl text-foreground">
                {msg('FE_CHECKOUT_SCHEDULED_CONFIRM_TITLE', 'Order scheduled')}
              </h2>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                {msg('FE_CHECKOUT_SCHEDULED_CONFIRM_BODY', "We'll start preparing it {date} at {time}.", {
                  date: placed.date || 'the next opening',
                  time: placed.time ? to12h(placed.time) : 'the first slot',
                })}
              </p>
              {placed.window && (
                <div className="mt-4 rounded-2xl border border-border bg-secondary/40 px-4 py-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Delivery window</p>
                  <p className="font-bold text-sm text-foreground mt-0.5">{placed.window}</p>
                </div>
              )}
              {placed.total != null && (
                <p className="mt-3 text-xs text-muted-foreground">Total {formatNaira(placed.total)} · pay when the kitchen starts your order.</p>
              )}
              <button
                onClick={onClose}
                className="mt-6 w-full py-3.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow active:scale-95 transition"
              >
                Done
              </button>
            </div>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    );
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4"
      >
        <motion.div
          initial={{ scale: 0.94, y: 24 }} animate={{ scale: 1, y: 0 }}
          className="bg-card rounded-3xl w-full max-w-sm overflow-hidden relative shadow-2xl"
        >
          <button onClick={onClose} aria-label="Close" className="absolute top-3 right-3 z-10 p-2 rounded-full bg-secondary/70 hover:bg-secondary transition-colors">
            <X size={ICON_SIZES.sm} className="text-muted-foreground" />
          </button>

          <div className="px-6 pt-8 pb-6 text-center">
            <FlameMark className="w-16 h-16 mx-auto mb-4" />
            <h2 className="font-heading font-extrabold text-xl text-foreground">
              {msg('FE_CHECKOUT_KITCHEN_CLOSED_TITLE', 'The kitchen is closed')}
            </h2>
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed">{body}</p>

            {nextDate && (
              <div className="mt-4 flex items-center justify-center gap-2 rounded-2xl border border-border bg-secondary/40 px-4 py-3">
                <Clock className="w-4 h-4 text-primary shrink-0" />
                <span className="text-sm font-bold text-foreground">
                  {watDate(nextDate)?.toLocaleDateString('en-NG', { weekday: 'long', day: 'numeric', month: 'short' }) || nextDate}
                  {nextTime ? ` · ${to12h(nextTime)}` : ''}
                </span>
              </div>
            )}

            <div className="mt-6 space-y-2">
              <button
                onClick={() => onSchedule(setPlaced)}
                disabled={busy}
                className="w-full py-3.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow flex items-center justify-center gap-2 active:scale-95 transition disabled:opacity-60"
              >
                {busy ? (
                  <><span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Scheduling…</>
                ) : (
                  <>{msg('FE_CHECKOUT_SCHEDULE_MY_ORDER', 'Schedule my order')} <ArrowRight size={ICON_SIZES.sm} /></>
                )}
              </button>
              <button
                onClick={onClose}
                disabled={busy}
                className="w-full py-2.5 text-sm text-muted-foreground font-semibold hover:text-foreground transition disabled:opacity-60"
              >
                {msg('FE_CHECKOUT_CANCEL', 'Cancel')}
              </button>
            </div>

            <p className="mt-3 text-[11px] text-muted-foreground flex items-center justify-center gap-1.5">
              <AlertCircle className="w-3 h-3 shrink-0" /> Nothing is charged until the kitchen accepts it.
            </p>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
