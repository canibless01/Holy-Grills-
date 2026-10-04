import React from 'react';
import { X } from 'lucide-react';

export function Toggle({ checked, onChange, disabled }: { checked?: boolean; onChange: (next: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`w-11 h-6 rounded-full p-0.5 transition-colors shrink-0 disabled:opacity-50 ${checked ? 'bg-gradient-cta' : 'bg-secondary'}`}
    >
      <div className={`w-5 h-5 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  );
}

export function Modal({ open, onClose, title, children }: { open?: boolean; onClose?: () => void; title?: React.ReactNode; children?: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-md p-4" onClick={onClose}>
      <div className="w-full sm:max-w-lg bg-white rounded-3xl shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white px-5 py-4 border-b border-border flex items-center justify-between z-10">
          <h3 className="font-heading font-extrabold text-base text-foreground">{title}</h3>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-secondary">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label?: React.ReactNode; children?: React.ReactNode; hint?: React.ReactNode }) {
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
      className={`w-full mt-1 p-2.5 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/60 ${props.className || ''}`}
    />
  );
}

// D1: this file used to define a SECOND Pill with its own tone map (Tailwind
// 100/700 pairs) while AdminKit exported one on brand tokens, so the same tone
// looked different depending on which module a page imported it from. There is
// now one implementation: re-exported here so the 25 admin files that import
// `<Pill>` from AdminShared keep working unchanged, on the brand palette.
export { Pill } from './ui/AdminKit';
export type { PillTone as AdminPillTone } from './ui/AdminKit';

export function Card({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-white border border-border p-4 ${className}`}>{children}</div>;
}

export function SectionHeader({ title, action }: { title?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <h3 className="font-bold text-sm text-foreground">{title}</h3>
      {action}
    </div>
  );
}