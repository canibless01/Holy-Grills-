import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useCampus } from '@/lib/campusContext';
import Skeleton from '@/components/Skeleton';

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
  const { campusId, campuses, campusesLoading, requireCampus, releaseCampus } = useCampus();
  const { pathname } = useLocation();
  const base = '/' + (pathname.split('/')[1] || '');
  const action = ACTION_BY_PATH[base] || 'continue';

  useEffect(() => {
    requireCampus(action);
    return () => releaseCampus();
  }, [base, action, requireCampus, releaseCampus]);

  if (campusId) return <Outlet />;

  // No campuses to choose (single-campus / no public list endpoint) — let the
  // backend fall back to global/unscoped data rather than trapping the guest.
  if (!campusesLoading && campuses.length === 0) return <Outlet />;

  if (campusesLoading) return (
    <div className="space-y-3 py-6">
      <Skeleton className="h-5 w-32" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
    </div>
  );

  // The gate is normally open on top of this. If it was dismissed, this button
  // is how the guest gets back to it — re-entering the route also re-opens it.
  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <h1 className="font-heading font-extrabold text-xl text-foreground">
        {TITLE_BY_PATH[base] || 'Choose your campus'}
      </h1>
      <button
        type="button"
        onClick={() => requireCampus(action)}
        className="mt-4 px-5 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold active:scale-95 transition"
      >
        Choose your campus
      </button>
    </div>
  );
}
