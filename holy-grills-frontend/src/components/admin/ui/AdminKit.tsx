import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

// UI kit scoped to the Admin Panel & User Management + Analytics domains.
// Other admin domains keep using AdminShared.jsx — nothing cross-domain changes.

// Pulls the payload out of a {status, message, data} envelope without
// inventing shapes — returns the response as-is when already unwrapped.
export const body = (res) =>
  res && typeof res === 'object' && !Array.isArray(res) && res.data && typeof res.data === 'object' ? res.data : res;

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-xl bg-secondary ${className}`}>
      <div className="absolute inset-0 shimmer-bg animate-shimmer" />
    </div>
  );
}

export function Card({ children, className = '', ...rest }: React.ComponentProps<'div'>) {
  return (
    <div className={`rounded-2xl bg-card border border-border shadow-card ${className}`} {...rest}>
      {children}
    </div>
  );
}

const PILL_TONES = {
  cocoa: 'bg-secondary text-secondary-foreground',
  flame: 'bg-primary/10 text-primary',
  green: 'bg-success/15 text-success',
  amber: 'bg-accent/25 text-accent-foreground',
  red: 'bg-destructive/10 text-destructive',
  outline: 'border border-border text-muted-foreground',
};

export function Pill({ children, tone = 'cocoa', className = '' }: { children?: ReactNode; tone?: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-full ${PILL_TONES[tone] || PILL_TONES.cocoa} ${className}`}>
      {children}
    </span>
  );
}

export function StatTile({ icon: Icon, label, value, sub, iconClass = 'text-primary', iconBg = 'bg-primary/10', className = '' }: {
  icon?: React.ElementType | null;
  label?: ReactNode;
  value?: ReactNode;
  sub?: ReactNode;
  iconClass?: string;
  iconBg?: string;
  className?: string;
}) {
  return (
    <Card className={`p-4 ${className}`}>
      <div className={`w-8 h-8 rounded-xl ${iconBg} flex items-center justify-center mb-2.5`}>
        {Icon && <Icon className={`w-4 h-4 ${iconClass}`} />}
      </div>
      <div className="font-heading font-extrabold text-xl text-foreground leading-tight">{value}</div>
      <div className="text-xs font-semibold text-foreground/70">{label}</div>
      {sub != null && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
    </Card>
  );
}

export function EmptyState({ icon: Icon, title, body: bodyText, action, className = '' }: {
  icon?: React.ElementType | null;
  title?: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center justify-center text-center py-10 px-4 ${className}`}>
      {Icon && (
        <div className="w-12 h-12 rounded-2xl bg-secondary flex items-center justify-center mb-3">
          <Icon className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      <div className="font-bold text-sm text-foreground">{title}</div>
      {bodyText && <p className="text-xs text-muted-foreground mt-0.5 max-w-xs">{bodyText}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function SectionTitle({ icon: Icon, title, sub, right }: {
  icon?: React.ElementType | null;
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 mb-3">
      <div className="flex items-center gap-2 min-w-0">
        {Icon && (
          <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <Icon className="w-3.5 h-3.5 text-primary" />
          </div>
        )}
        <div className="min-w-0">
          <h3 className="font-heading font-extrabold text-sm text-foreground truncate">{title}</h3>
          {sub && <p className="text-[11px] text-muted-foreground truncate">{sub}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

export function Segmented({ options, value, onChange, className = '' }: {
  options: Array<{ id: string; label: ReactNode; icon?: React.ElementType | null }>;
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={`inline-flex gap-1 p-1 rounded-full bg-secondary border border-border ${className}`}>
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          className={`flex items-center justify-center gap-1.5 px-4 py-2 rounded-full text-xs font-bold transition-all active:scale-95 ${value === o.id ? 'bg-card text-primary shadow-card' : 'text-muted-foreground hover:text-foreground'}`}
        >
          {o.icon && <o.icon className="w-3.5 h-3.5" />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide = false }: {
  open?: boolean;
  onClose?: () => void;
  title?: ReactNode;
  children?: ReactNode;
  wide?: boolean;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-foreground/50 backdrop-blur-sm sm:p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 48, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 32, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            className={`w-full ${wide ? 'sm:max-w-2xl' : 'sm:max-w-md'} bg-card rounded-t-3xl sm:rounded-3xl shadow-card max-h-[92vh] overflow-y-auto`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-card px-5 py-4 border-b border-border flex items-center justify-between z-10">
              <h3 className="font-heading font-extrabold text-base text-foreground">{title}</h3>
              <button onClick={onClose} className="p-2 -mr-2 rounded-xl hover:bg-secondary active:scale-95 transition">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
            <div className="p-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Field({ label, children, hint }: { label?: ReactNode; children?: ReactNode; hint?: ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wide">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}

export function TextInput(props: React.ComponentProps<'input'>) {
  return (
    <input
      {...props}
      className={`w-full mt-1 px-3 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60 transition ${props.className || ''}`}
    />
  );
}

export function Toggle({ checked, onChange, disabled }: { checked?: boolean; onChange: (next: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`w-11 h-6 rounded-full p-0.5 transition-colors shrink-0 disabled:opacity-50 ${checked ? 'bg-gradient-cta' : 'bg-secondary border border-border'}`}
    >
      <div className={`w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  );
}

export function Pagination({ page, canPrev, canNext, onPrev, onNext, busy = false }: {
  page: number;
  canPrev?: boolean;
  canNext?: boolean;
  onPrev?: () => void;
  onNext?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] font-bold text-muted-foreground">Page {page + 1}</span>
      <div className="flex gap-1.5">
        <button
          onClick={onPrev}
          disabled={!canPrev || busy}
          className="px-4 py-1.5 rounded-full text-xs font-bold bg-card border border-border text-foreground disabled:opacity-40 hover:border-primary/50 active:scale-95 transition"
        >
          Prev
        </button>
        <button
          onClick={onNext}
          disabled={!canNext || busy}
          className="px-4 py-1.5 rounded-full text-xs font-bold bg-card border border-border text-foreground disabled:opacity-40 hover:border-primary/50 active:scale-95 transition"
        >
          {busy ? '…' : 'Next'}
        </button>
      </div>
    </div>
  );
}

// Generic renderer for analytics payloads whose exact shape the API docs
// leave as an empty envelope: shows whatever numeric fields the backend
// actually returns, with an honest empty state — nothing invented.
export function BreakdownTiles({ data, emptyTitle = 'Nothing here yet', formatValue = (v: unknown) => v as ReactNode }: {
  data?: Record<string, unknown> | null;
  emptyTitle?: string;
  formatValue?: (v: unknown) => ReactNode;
}) {
  const entries: Array<[string, unknown]> = Object.entries(data || {})
    .filter(([, v]) => v != null && typeof v !== 'object')
    .map(([k, v]) => [k.replace(/_/g, ' '), v]);
  if (!entries.length) {
    return <p className="text-xs text-muted-foreground text-center py-6">{emptyTitle}</p>;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
      {entries.map(([label, value]) => (
        <div key={label} className="rounded-xl bg-secondary/50 border border-border px-3 py-2.5">
          <div className="text-[10px] font-extrabold uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="font-heading font-extrabold text-sm text-foreground mt-0.5">{formatValue(value)}</div>
        </div>
      ))}
    </div>
  );
}