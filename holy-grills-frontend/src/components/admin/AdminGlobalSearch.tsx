import { useState, useRef, useEffect } from 'react';
import { Search, X, ArrowRight, LayoutGrid } from 'lucide-react';
import { matchSections } from '@/lib/adminSections';

// Section-only search — jumps straight to an admin page/section by intent.
// Data-record search (orders, users, menu items, promo codes) was removed:
// the admin already knows where those live in the sidebar, and the record
// results returned opaque codes/IDs that were not actionable. This now focuses
// purely on navigating to the right section ("revenue" → Analytics, etc.).
export default function AdminGlobalSearch({ onNavigate }) {
  const [q, setQ] = useState('');
  const [focused, setFocused] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setFocused(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const close = () => { setQ(''); setFocused(false); };
  const open = focused && q.trim().length >= 1;
  const sectionMatches = open ? matchSections(q) : [];

  return (
    <div className="relative" ref={wrapRef}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 w-4 h-4 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocused(true)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') close();
            if (e.key === 'Enter' && sectionMatches[0] && onNavigate) { onNavigate(sectionMatches[0].id); close(); }
          }}
          placeholder="Search admin sections…"
          className="w-full pl-9 pr-8 py-2 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 transition"
        />
        {q && (
          <button onClick={close} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-secondary active:scale-95 transition">
            <X className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        )}
      </div>

      {open && (
        <div className="absolute top-full mt-1.5 left-0 right-0 z-50 bg-card rounded-2xl border border-border shadow-card max-h-[400px] overflow-y-auto overflow-x-hidden">
          {sectionMatches.length === 0 ? (
            <div className="p-4 text-center text-xs font-semibold text-muted-foreground">No sections match “{q}”.</div>
          ) : (
            <div>
              <div className="flex items-center gap-2 px-3 py-2 bg-primary/5 sticky top-0">
                <LayoutGrid className="w-3.5 h-3.5 text-primary" />
                <span className="text-[10px] font-extrabold text-foreground uppercase tracking-wider">Pages</span>
                <span className="text-[10px] text-muted-foreground font-bold">({sectionMatches.length})</span>
              </div>
              {sectionMatches.map((s) => {
                const Icon = s.icon;
                return (
                  <button
                    key={s.id}
                    onClick={() => { if (onNavigate) onNavigate(s.id); close(); }}
                    className="w-full text-left px-3 py-2.5 hover:bg-primary/5 transition flex items-center gap-2.5"
                  >
                    <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <Icon className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-bold text-foreground truncate">{s.label}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{s.desc}</div>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-primary shrink-0" />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}