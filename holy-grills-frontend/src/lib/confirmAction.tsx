import { createRoot } from 'react-dom/client';
import { X, AlertTriangle } from 'lucide-react';

/**
 * ConfirmDialog — the brand's replacement for the browser's native confirm().
 *
 * Native dialogs match nothing in the design system, are un-dismissable on
 * some platforms, and say "chrome" instead of "Holy Grills". This renders the
 * same visual language as every other popup (hg-scrim veil, card, brand
 * buttons) and resolves a Promise<boolean> so call-sites stay one-liners:
 *
 *   if (!(await confirmAction({ title: 'Cancel this batch?', confirmLabel: 'Cancel batch', destructive: true }))) return;
 *
 * The dialog mounts its own React root on a detached <body> child, so it works
 * from anywhere (event handlers, admin tables, pages) with zero state wiring.
 */
export interface ConfirmOptions {
  title: string;
  body?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button — use when the action removes/cancels something. */
  destructive?: boolean;
}

export function confirmAction(opts: ConfirmOptions): Promise<boolean> {
  if (typeof document === 'undefined') return Promise.resolve(false);
  return new Promise((resolve) => {
    const host = document.createElement('div');
    host.setAttribute('data-hg-confirm', '');
    document.body.appendChild(host);
    const done = (result: boolean) => {
      // Resolve first, then unmount on the next tick so the click that
      // answered the dialog can never land inside the removing node.
      resolve(result);
      setTimeout(() => { root.unmount(); host.remove(); }, 0);
    };
    const root = createRoot(host);
    root.render(<ConfirmDialog {...opts} onResult={done} />);
  });
}

function ConfirmDialog({ title, body, confirmLabel = 'Confirm', cancelLabel = 'Go back', destructive = false, onResult }: ConfirmOptions & { onResult: (v: boolean) => void }) {
  return (
    <div
      className="fixed inset-0 z-[80] hg-scrim flex items-end sm:items-center justify-center p-4 animate-fade-in"
      onClick={() => onResult(false)}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onKeyDown={(e) => { if (e.key === 'Escape') onResult(false); }}
    >
      <div
        className="bg-card rounded-3xl p-6 w-full max-w-xs sm:max-w-sm shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className={`w-9 h-9 rounded-2xl flex items-center justify-center shrink-0 ${destructive ? 'bg-destructive/10' : 'bg-primary/10'}`}>
              <AlertTriangle className={`w-4.5 h-4.5 w-[18px] h-[18px] ${destructive ? 'text-destructive' : 'text-primary'}`} />
            </div>
            <h3 className="font-heading font-extrabold text-base text-foreground leading-tight">{title}</h3>
          </div>
          <button onClick={() => onResult(false)} aria-label="Close" className="p-1.5 -mr-1 -mt-1 rounded-full hover:bg-secondary transition-colors shrink-0">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
        {body && <p className="text-sm text-muted-foreground leading-relaxed mb-5">{body}</p>}
        {!body && <div className="h-4" />}
        <div className="flex gap-2">
          <button
            onClick={() => onResult(false)}
            className="flex-1 py-2.5 rounded-full border border-border text-foreground text-sm font-bold hover:bg-secondary active:scale-[0.98] transition"
          >
            {cancelLabel}
          </button>
          <button
            autoFocus
            onClick={() => onResult(true)}
            className={`flex-1 py-2.5 rounded-full text-white text-sm font-bold active:scale-[0.98] transition ${destructive ? 'bg-destructive' : 'bg-primary'}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
