import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';

// Domain 0 — route guard for campus-scoped pages.
//
// A guest with no campus chosen must NOT see the page: the menu, cart, checkout,
// events, marketplace and leaderboard all resolve their data from a campus, so
// rendering them unscoped is what produced the "no menu items / retry" screen —
// the page mounted, asked the API for a campus it did not have, and got nothing.
//
// So: withhold the content, and let the CampusGate modal (rendered globally by
// CampusProvider) be the single place a campus is chosen. What renders here is a
// compact placeholder — a real <h1> so the route stays indexable, and one button
// back into the picker for a guest who dismissed it. No second copy of the
// campus list, and no explanatory copy.
//
// Authenticated users pass straight through (scoped by their own campus_id).
// Static pages (Home, FAQ, Terms, Our Story) are intentionally NOT wrapped here.
const ACTION_BY_PATH = {
  '/menu': 'browse the menu',
  '/cart': 'review your cart',
  '/checkout': 'place your order',
  '/events': 'see campus events',
  '/marketplace': 'open the marketplace',
  '/leaderboard': 'view the leaderboard',
};

// What the build-time pre-render writes into the HTML for these routes, so the
// URLs still carry indexable content instead of an empty shell.
const TITLE_BY_PATH: Record<string, string> = {
  '/menu': "Today's menu",
  '/events': 'Campus events',
  '/marketplace': 'The campus marketplace',
  '/leaderboard': 'The Holy Grills leaderboard',
};

export default function CampusScope() {
  const { user, isLoading } = useHolyGrill();
  const { campusId, campuses, campusesLoading, requireCampus, releaseCampus, openGate } = useCampus();
  const { pathname } = useLocation();
  const base = '/' + (pathname.split('/')[1] || '');
  const action = ACTION_BY_PATH[base] || 'continue';

  useEffect(() => {
    requireCampus(action);
    return () => releaseCampus();
  }, [base, action, requireCampus, releaseCampus]);

  // A signed-in user is scoped server-side by their own campus_id (set at
  // registration, never changeable). They must never be asked to pick one —
  // and must never see this placeholder. This is checked BEFORE campusId,
  // because the profile's campus_id can still be in flight on first paint.
  if (user) return <Outlet />;
  // Auth still resolving: render the page rather than flashing a picker at
  // someone who is about to be recognised. requireCampus() re-runs when `user`
  // lands and opens the gate if it really is a guest.
  if (isLoading) return <Outlet />;
  if (campusId) return <Outlet />;

  // No campuses to choose (single-campus / no public list endpoint) — let the
  // backend fall back to global/unscoped data rather than trapping the guest.
  if (!campusesLoading && campuses.length === 0) return <Outlet />;

  // The gate is normally open on top of this. If it was dismissed, the button
  // below is how the guest gets back to it — re-entering the route re-opens it.
  // It calls openGate() directly, not requireCampus(): requireCampus() returns
  // true (and opens nothing) as soon as it sees a `user` object, which is what
  // left this as a dead-end button for a signed-in user whose campus_id had not
  // resolved yet.
  //
  // This placeholder is client-only by design. `isLoading` starts true, so both
  // the build-time pre-render and the client's first render take the `<Outlet/>`
  // branch above — that match is what keeps hydration intact. The SEO copy for
  // these routes lives in the route's own <title>/JSON-LD, not here.
  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <h1 className="font-heading font-extrabold text-xl text-foreground">
        {TITLE_BY_PATH[base] || 'Choose your campus'}
      </h1>
      <button
        type="button"
        onClick={() => openGate(action, 'blocking')}
        className="mt-4 px-5 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold active:scale-95 transition"
      >
        Choose your campus
      </button>
    </div>
  );
}
