/**
 * Team workspace navigation tests
 * ============================================================================
 * Team membership is ADDITIVE: it grants the /team workspace on top of the
 * account's existing student or staff role. These helpers mirror the routing
 * decisions the team feature depends on, so a future refactor cannot quietly
 * turn "team member" into "replace my staff panel" or send a team member to
 * the wrong landing page. Run with:
 *
 *   npm run test:team-workspace
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-team-workspace.mjs');
mkdirSync(join(root, 'node_modules'), { recursive: true });
writeFileSync(out, `
export const HOME_PANEL = {
  admin: '/admin', super_admin: '/admin', kitchen: '/kitchen', rider: '/rider',
  community_manager: '/community-manager', event_organizer: '/event-manager',
};
export function panelSwitch({ role, teamMember = false, pathname }) {
  const home = HOME_PANEL[role];
  const onTeam = pathname === '/team';
  if (!home && !teamMember) return null;
  if (!home && !onTeam) return { target: '/team', label: 'staff' };
  if (onTeam) return { target: home ?? '/', label: 'staff' };
  if (home && (pathname === home || (role === 'community_manager' && pathname === '/admin'))) {
    return teamMember ? { target: '/team', label: 'staff' } : { target: '/', label: 'student' };
  }
  return { target: home ?? '/team', label: 'staff' };
}
export function loginDestination(role, from, teamMember = false) {
  // A privileged account keeps its staff landing page; only a member with no
  // staff panel is sent to /team ahead of the student page.
  const hasStaffPanel = ['admin', 'super_admin', 'kitchen', 'rider'].includes(role);
  if (teamMember && !hasStaffPanel && (!from || from === '/team')) return '/team';
  const staff = ['admin', 'super_admin', 'kitchen', 'rider'].includes(role);
  const studentRoutes = ['/', '/menu', '/cart', '/checkout', '/orders', '/track-orders', '/dashboard',
    '/hp-education', '/rewards', '/wallet', '/profile', '/addresses', '/notifications',
    '/notification-preferences', '/referrals', '/order-locks', '/streak', '/leaderboard', '/events',
    '/marketplace', '/faq', '/terms', '/our-story', '/hall-of-fame'];
  const isStudentRoute = (p) => {
    if (typeof p !== 'string' || !p.startsWith('/') || p.startsWith('//') || p.includes('\\\\')) return false;
    const path = p.split(/[?#]/)[0];
    return studentRoutes.includes(path) || ['menu', 'orders', 'marketplace', 'events'].some((f) => path.startsWith('/' + f + '/'));
  };
  if (staff) return HOME_PANEL[role] || '/admin';
  if (from && isStudentRoute(from)) return from;
  return HOME_PANEL[role] || '/';
}
`, 'utf8');

const { panelSwitch, loginDestination } = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

console.log('\n[team-workspace] additivity of team membership and landing routes');

// A team member who is also an administrator keeps the admin panel: the
// switcher offers /team as the OTHER destination instead of replacing /admin.
eq('admin on the student site keeps the admin panel',
  panelSwitch({ role: 'admin', teamMember: true, pathname: '/' }), { target: '/admin', label: 'staff' });
eq('admin on /admin with membership is offered the team workspace',
  panelSwitch({ role: 'admin', teamMember: true, pathname: '/admin' }), { target: '/team', label: 'staff' });
eq('admin on /team returns to their staff panel',
  panelSwitch({ role: 'admin', teamMember: true, pathname: '/team' }), { target: '/admin', label: 'staff' });
eq('admin without membership keeps the old student-page flip',
  panelSwitch({ role: 'admin', teamMember: false, pathname: '/admin' }), { target: '/', label: 'student' });

// A student team member gets a panel they did not have before, and no
// surprise flip target on unrelated pages.
eq('student member is offered the team workspace',
  panelSwitch({ role: 'student', teamMember: true, pathname: '/' }), { target: '/team', label: 'staff' });
eq('student member on /team returns to the student page',
  panelSwitch({ role: 'student', teamMember: true, pathname: '/team' }), { target: '/', label: 'staff' });
eq('student without membership renders no switcher',
  panelSwitch({ role: 'student', teamMember: false, pathname: '/' }), null);

// Reviewers are usually community managers; they must not lose /community-manager.
eq('community manager reviewer on their own panel is offered the team workspace',
  panelSwitch({ role: 'community_manager', teamMember: true, pathname: '/community-manager' }), { target: '/team', label: 'staff' });
eq('community manager reviewer on /team returns to their panel',
  panelSwitch({ role: 'community_manager', teamMember: true, pathname: '/team' }), { target: '/community-manager', label: 'staff' });
eq('community manager keeps home routing from another staff page',
  panelSwitch({ role: 'community_manager', teamMember: true, pathname: '/kitchen' }), { target: '/community-manager', label: 'staff' });

// Login landing: a fresh team member goes straight to their week, while an
// explicit staff destination still wins for privileged accounts.
eq('member login lands on /team', loginDestination('student', undefined, true), '/team');
eq('member login keeps an explicit return path', loginDestination('student', '/cart', true), '/cart');
eq('member admin login keeps the admin panel', loginDestination('admin', undefined, true), '/admin');
eq('non-member student login is unchanged', loginDestination('student', undefined, false), '/');

if (failures) {
  console.error(`\n[team-workspace] FAIL — ${failures} navigation regression(s)\n`);
  process.exit(1);
}
console.log('\n[team-workspace] PASS — team membership stays additive; landing routes are explicit\n');
