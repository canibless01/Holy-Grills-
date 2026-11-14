import { MapPin, Globe2 } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';
import { useIsSuperAdmin } from './SuperAdminGate';
import { msg } from '@/lib/messages';

/**
 * The campus scope every admin WRITE in this panel will land on. It is resolved
 * from the exact switcher state apiClient sends to the backend
 * (X-Campus-ID for a selected campus, X-Campus-Scope: global on "All Campuses"):
 *
 *   super admin + selected campus -> that campus
 *   super admin + "All Campuses"  -> Global (the row is written with campus_id NULL)
 *   campus admin                  -> their own assigned campus (read-only)
 *
 * Use the hook for write-time guards/confirmations; render <AdminScopeBadge />
 * wherever a save button lives so the target scope is never a surprise.
 */
export function useAdminWriteScope() {
  const isSuperAdmin = useIsSuperAdmin();
  const { campusId, adminCampusId, adminCampus, campuses } = useCampus();
  const isGlobal = !!isSuperAdmin && !adminCampusId;
  const targetCampusId = isSuperAdmin ? (adminCampusId || null) : (campusId || null);
  const ownName = campuses.find((c) => c.id === campusId)?.name || '';
  const campusName = isSuperAdmin ? (adminCampus?.name || '') : ownName;
  const label = isGlobal
    ? msg('FE_ADMIN_SCOPE_GLOBAL', 'Global')
    : campusName || msg('FE_ADMIN_SCOPE_SELECTED_CAMPUS', 'Selected campus');
  return { isSuperAdmin, isGlobal, targetCampusId, campusName, label };
}

export default function AdminScopeBadge({ className = '' }: { className?: string }) {
  const { isGlobal, label } = useAdminWriteScope();
  const Icon = isGlobal ? Globe2 : MapPin;
  return (
    <div
      data-testid="admin-scope-badge"
      title={msg(
        'FE_ADMIN_SCOPE_BADGE_HINT',
        'Every save from this panel writes to this scope. Global rows apply on every campus unless a campus-specific row overrides them.',
      )}
      className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-2.5 py-1.5 text-[11px] font-bold text-foreground shrink-0 ${className}`}
    >
      <Icon className="w-3.5 h-3.5 text-primary shrink-0" />
      <span className="truncate max-w-[220px]">
        {msg('FE_ADMIN_SCOPE_SAVING_TO', 'Saving to: {scope}', { scope: label })}
      </span>
    </div>
  );
}
