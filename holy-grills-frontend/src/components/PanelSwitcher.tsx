import { Link, useLocation } from 'react-router-dom';
import { ArrowLeftRight } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';

const HOME_PANEL: Record<string, string> = {
  admin: '/admin',
  super_admin: '/admin',
  kitchen: '/kitchen',
  rider: '/rider',
};
const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  super_admin: 'Admin',
  kitchen: 'Kitchen',
  rider: 'Rider',
};

/**
 * PanelSwitcher — ONE small icon that rotates a staff member between the
 * student site and their home panel, wherever they are:
 *   • on the student page      → opens their home panel (admin → /admin)
 *   • on their home panel      → flips to the student page
 *   • on another staff panel   → returns them home (admin on Kitchen or
 *     Rider → back to /admin)
 * Renders nothing for non-staff users. Styling is supplied by whichever
 * header mounts it, so it blends into that header's existing action row.
 */
export default function PanelSwitcher({ className = '', labelClassName = undefined }: { className?: string; labelClassName?: string | null }) {
  const { user } = useHolyGrill();
  const { pathname } = useLocation();
  const home = user ? HOME_PANEL[user.role] : undefined;
  if (!home) return null;

  const onHomePanel = pathname === home;
  const target = onHomePanel ? '/' : home;
  const roleLabel = ROLE_LABEL[user.role] ?? 'Panel';
  const title = onHomePanel ? 'View student page' : `Open ${roleLabel} panel`;

  return (
    <Link to={target} className={className} aria-label={title} title={title}>
      <ArrowLeftRight className="w-3.5 h-3.5" />
      {labelClassName && (
        <span className={labelClassName}>{onHomePanel ? 'Student page' : `${roleLabel} panel`}</span>
      )}
    </Link>
  );
}
