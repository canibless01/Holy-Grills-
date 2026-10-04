import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ICONS, ICON_SIZES } from '@/config/icons';
import FlameMark from '@/components/FlameMark';
import ScheduleOrderPanel from '@/components/ScheduleOrderPanel';

const { X, ArrowRight } = ICONS;

/**
 * KitchenClosedPopup — shown ONLY when the storefront reports an explicit
 * closed state (the ordering window is over, or a date override closed the
 * store). It never shows while the state is unknown (no campus chosen), so a
 * guest who hasn't picked a campus is never told the kitchen is closed.
 *
 * Backend times are West Africa Time (UTC+1) — the countdown anchors to that
 * so it stays correct on any device timezone.
 *
 * Dismissed state persists for the session so it doesn't nag.
 */

const watDate = (date, time) => (date && time ? new Date(`${date}T${time.length === 5 ? time + ':00' : time}+01:00`) : null);

const parts = (ms) => {
  const total = Math.max(0, Math.floor(ms / 1000));
  return { h: Math.floor(total / 3600), m: Math.floor((total % 3600) / 60), s: total % 60 };
};
const pad = (n) => String(n).padStart(2, '0');

export default function KitchenClosedPopup({ status, scheduledWindows = [] }) {
  const [open, setOpen] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [now, setNow] = useState(Date.now());

  const dismissed = typeof window !== 'undefined' && sessionStorage.getItem('hg_kc_dismissed') === '1';

  // Explicit closed only — `unknown` (no campus yet) must never trigger this.
  useEffect(() => {
    if (status && status.unknown !== true && status.is_open === false && !dismissed) setOpen(true);
  }, [status, dismissed]);

  // Live clock — drives the reopening countdown.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const opensAt = watDate(status?.next_available_date, status?.next_opens_at);
  const remaining = opensAt ? opensAt.getTime() - now : null;
  const t = remaining != null ? parts(remaining) : null;
  const openingSoon = remaining != null && remaining <= 3600000;

  const close = () => {
    setOpen(false);
    try { sessionStorage.setItem('hg_kc_dismissed', '1'); } catch { /* ignore */ }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4"
        >
          <motion.div
            initial={{ scale: 0.94, y: 24 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 240, damping: 24 }}
            className="bg-card rounded-3xl w-full max-w-sm overflow-hidden relative shadow-2xl"
          >
            <button onClick={close} aria-label="Close" className="absolute top-3 right-3 z-10 p-2 rounded-full bg-secondary/70 hover:bg-secondary transition-colors">
              <X size={ICON_SIZES.sm} className="text-muted-foreground" />
            </button>

            {!scheduling ? (
              <div className="px-6 pt-8 pb-6 text-center">
                <FlameMark className="w-16 h-16 mx-auto mb-4" />
                <h2 className="font-heading font-extrabold text-xl text-foreground">The grill is resting 🔥</h2>
                <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">Next window soon.</p>

                {t && (
                  <div className="mt-5">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Opens in</p>
                    <div className="flex items-stretch justify-center gap-2">
                      {[
                        { v: pad(t.h), l: 'hrs' },
                        { v: pad(t.m), l: 'min' },
                        { v: pad(t.s), l: 'sec' },
                      ].map((seg) => (
                        <div key={seg.l} className={`flex-1 rounded-2xl border py-3 ${openingSoon ? 'border-success/30 bg-success/10' : 'border-border bg-secondary/40'}`}>
                          <div className={`font-heading font-extrabold text-2xl tabular-nums leading-none ${openingSoon ? 'text-success' : 'text-foreground'}`}>{seg.v}</div>
                          <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground mt-1">{seg.l}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-6 space-y-2">
                  <button
                    onClick={() => setScheduling(true)}
                    className="w-full py-3.5 rounded-full bg-gradient-cta text-white font-bold text-sm shadow-glow flex items-center justify-center gap-2 active:scale-95 transition"
                  >
                    Schedule my order <ArrowRight size={ICON_SIZES.sm} />
                  </button>
                  <button onClick={close} className="w-full py-2 text-sm text-muted-foreground font-semibold hover:text-foreground transition">
                    Maybe later
                  </button>
                </div>
              </div>
            ) : (
              <div className="px-6 pt-8 pb-6">
                <ScheduleOrderPanel
                  status={status}
                  windows={scheduledWindows}
                  onBack={() => setScheduling(false)}
                  onConfirm={() => { setOpen(false); setScheduling(false); }}
                />
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}