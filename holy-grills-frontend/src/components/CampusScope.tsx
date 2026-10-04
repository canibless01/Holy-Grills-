import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useCampus } from '@/lib/campusContext';
import Skeleton from '@/components/Skeleton';

// Domain 0 — route guard for campus-scoped pages. Guests without a selected
// campus get the non-cancelable CampusGate (rendered globally by CampusProvider)
// and the page content is withheld until a campus is chosen. Authenticated
// users pass straight through (scoped by their own campus_id). Static pages
// (Home, FAQ, Terms, Our Story) are intentionally NOT wrapped here.
const ACTION_BY_PATH = {
  '/menu': 'browse the menu',
  '/cart': 'review your cart',
  '/checkout': 'place your order',
  '/events': 'see campus events',
  '/marketplace': 'open the marketplace',
  '/leaderboard': 'view the leaderboard',
};

export default function CampusScope() {
  const { campusId, campuses, campusesLoading, requireCampus } = useCampus();
  const { pathname } = useLocation();

  useEffect(() => {
    const base = '/' + (pathname.split('/')[1] || '');
    requireCampus(ACTION_BY_PATH[base] || 'continue');
  }, [pathname, requireCampus]);

  if (campusId) return <Outlet />;
  if (campusesLoading) return (
    <div className="space-y-3 py-6">
      <Skeleton className="h-5 w-32" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
      <Skeleton className="h-10 w-full rounded-xl" />
    </div>
  );
  // No campuses to choose (single-campus / no public list endpoint) — let the
  // backend fall back to global/unscoped data rather than trapping the guest.
  if (campuses.length === 0) return <Outlet />;
  // Gate is open (set by requireCampus) and shown globally; withhold content.
  return null;
}