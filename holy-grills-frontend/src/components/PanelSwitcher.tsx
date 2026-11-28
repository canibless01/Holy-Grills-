import { msg } from '@/lib/messages';
import { Link, useLocation } from 'react-router-dom';
import { ArrowLeftRight } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';

const HOME_PANEL: Record<string, string> = {
  admin: '/admin',
  super_admin: '/admin',
  kitchen: '/kitchen',
  rider: '/rider',
  community_manager: '/community-manager',
  event_organizer: '/event-manager',
};
const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  super_admin: 'Admin',
  kitchen: 'Kitchen',
  rider: 'Rider',
  community_manager: 'Community Manager',
  event_organizer: msg('FE_ROLE_EVENT_ORGANIZER', 'Event Organizer'),
};

/**
 * PanelSwitcher — ONE small icon that rotates a staff member (and a team
 * member) between the student site and the panel they belong to, wherever
 * they are:
 *   • student page              → opens their home panel (admin → /admin)
 *   • on their home panel       → flips to the student page
 *   • on another staff panel    → returns them home (admin on Kitchen or
 *                                 Rider → back to /admin)
 *
 * Team membership is ADDITIVE, so it never replaces a staff panel: an admin
 * who is also on a team keeps /admin and the switcher offers /team as the
 * other destination. A student team member gets /team ↔ student page.
 * Renders nothing for accounts with no panel at all. Styling is supplied by
 * whichever header mounts it, so it blends into that header's existing
 * action row.
 */
export default function PanelSwitcher({ className = '', labelClassName = undefined }: { className?: string; labelClassName?: string | null }) {
  const { user } = useHolyGrill();
  const { pathname } = useLocation();
  const home = user ? HOME_PANEL[user.role] : undefined;
  const onTeam = pathname === '/team';
  const teamMember = !!user?.profile?.team_workspace;
  if (!home && !teamMember) return null;
  if (!home && !onTeam) {
    // Student team member: /team is the only panel they have.
    const title = msg('FE_TEAM_TEAM_LABEL', 'Team') + ' panel';
    return (
      <Link to="/team" className={className} aria-label={title} title={title}>
        <ArrowLeftRight className="w-3.5 h-3.5" />
        {labelClassName && <span className={labelClassName}>{title}</span>}
      </Link>
    );
  }

  const staffLabel = home ? `${ROLE_LABEL[user.role] ?? 'Panel'} panel` : msg('FE_TEAM_TEAM_LABEL', 'Team') + ' panel';
  const studentLabel = msg('FE_PANEL_STUDENT', 'View student page');
  let target = home ?? '/team';
  let label = staffLabel;
  if (onTeam) {
    target = home ?? '/';
    label = home ? staffLabel : studentLabel;
  } else if (home && (pathname === home || (user.role === 'community_manager' && pathname === '/admin'))) {
    // Already on the home panel: offer the team workspace when they have one,
    // otherwise the student page (the previous behaviour).
    target = teamMember ? '/team' : '/';
    label = teamMember ? staffLabel : studentLabel;
  }
  const title = label === studentLabel ? studentLabel : msg('FE_PANEL_OPEN', 'Open {role} panel', { role: label.replace(/ panel$/, '') });

  return (
    <Link to={target} className={className} aria-label={title} title={title}>
      <ArrowLeftRight className="w-3.5 h-3.5" />
      {labelClassName && <span className={labelClassName}>{label}</span>}
    </Link>
  );
}
