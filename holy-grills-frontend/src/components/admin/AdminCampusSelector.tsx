import { useState, useRef, useEffect } from 'react';
import { MapPin, ChevronDown, Check } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';

// Domain 0 — admin campus switcher. Super-admins can view/manage any campus;
// the selection is persisted in localStorage (hg_admin_campus_id) and sent as
// X-Campus-ID by apiClient. Regular admins are scoped to their own campus
// (JWT campus_id) and see a read-only badge — no selector shown.
export default function AdminCampusSelector() {
  const { user } = useHolyGrill();
  const { campuses, adminCampusId, adminCampus, selectAdminCampus } = useCampus();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const isSuperAdmin = user?.role === 'super_admin';
  useEffect(() => {
    if (!isSuperAdmin) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isSuperAdmin]);

  // Regular admin — show their own campus as a read-only badge (or "All" if
  // the campus list hasn't loaded yet). No dropdown, no switching.
  if (!isSuperAdmin) {
    // Show the admin's own campus by name (from the campus list, or the campus
    // carried on their profile). Read-only — a regular admin is scoped to it.
    const name =
      campuses.find((c) => c.id === user?.campus_id)?.name ||
      (typeof user?.campus === 'string' ? user.campus : user?.campus?.name) ||
      'My Campus';
    return (
      <div
        title={name}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary text-xs font-bold text-foreground shrink-0"
      >
        <MapPin className="w-3.5 h-3.5 text-primary shrink-0" />
        <span className="truncate max-w-[84px] sm:max-w-[140px]">{name}</span>
      </div>
    );
  }

  // Super-admin — dropdown to switch between campuses. Defaults to "All
  // Campuses" (no X-Campus-ID header) when no campus is selected.
  const label = adminCampus?.name || 'All Campuses';
  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-muted text-xs font-bold text-foreground transition-colors"
      >
        <MapPin className="w-3.5 h-3.5 text-primary shrink-0" />
        <span className="truncate max-w-[84px] sm:max-w-[140px]">{label}</span>
        <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 rounded-xl border border-border bg-popover shadow-card z-50 overflow-hidden">
          <button
            onClick={() => { selectAdminCampus(null); setOpen(false); }}
            className={`w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-foreground hover:bg-secondary transition-colors ${!adminCampusId ? 'text-primary' : ''}`}
          >
            All Campuses
            {!adminCampusId && <Check className="w-3.5 h-3.5" />}
          </button>
          {campuses.map((c) => (
            <button
              key={c.id}
              onClick={() => { selectAdminCampus(c.id); setOpen(false); }}
              className={`w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-foreground hover:bg-secondary transition-colors ${c.id === adminCampusId ? 'text-primary' : ''}`}
            >
              <span className="truncate">{c.name}</span>
              {c.id === adminCampusId && <Check className="w-3.5 h-3.5 shrink-0" />}
            </button>
          ))}
          {campuses.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">No campuses available</div>
          )}
        </div>
      )}
    </div>
  );
}