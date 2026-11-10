import { lazy, Suspense } from 'react';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { msg } from '@/lib/messages';
import { Navigate, useSearchParams } from 'react-router-dom';
import { ShieldAlert, LogOut } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import BrandLogo from '@/components/BrandLogo';
import AdminLayout from '@/components/admin/AdminLayout';
const AdminDashboard = lazy(() => import('@/components/admin/AdminDashboard'));
const AdminAnalytics = lazy(() => import('@/components/admin/AdminAnalytics'));
const AdminWalletAnalytics = lazy(() => import('@/components/admin/AdminWalletAnalytics'));
const AdminEconomics = lazy(() => import('@/components/admin/AdminEconomics'));
const AdminUsers = lazy(() => import('@/components/admin/AdminUsers'));
const AdminOrders = lazy(() => import('@/components/admin/AdminOrders'));
const AdminDelivery = lazy(() => import('@/components/admin/AdminDelivery'));
const AdminPromos = lazy(() => import('@/components/admin/AdminPromos'));
const AdminFeatureFlags = lazy(() => import('@/components/admin/AdminFeatureFlags'));
const AdminSystemSettings = lazy(() => import('@/components/admin/AdminSystemSettings'));
const AdminSystem = lazy(() => import('@/components/admin/AdminSystem'));
const AdminMenu = lazy(() => import('@/components/admin/AdminMenu'));
const AdminAddons = lazy(() => import('@/components/admin/AdminAddons'));
const AdminEvents = lazy(() => import('@/components/admin/AdminEvents'));
const AdminRewards = lazy(() => import('@/components/admin/AdminRewards'));
const AdminMarketplace = lazy(() => import('@/components/admin/AdminMarketplace'));
const AdminNotifications = lazy(() => import('@/components/admin/AdminNotifications'));
const AdminLeaderboard = lazy(() => import('@/components/admin/AdminLeaderboard'));
const AdminDepartments = lazy(() => import('@/components/admin/AdminDepartments'));
const AdminStorefront = lazy(() => import('@/components/admin/AdminStorefront'));
const AdminOnboarding = lazy(() => import('@/components/admin/AdminOnboarding'));
const AdminCampuses = lazy(() => import('@/components/admin/AdminCampuses'));
const AdminHpMultipliers = lazy(() => import('@/components/admin/AdminHpMultipliers'));
const AdminChallenges = lazy(() => import('@/components/admin/AdminChallenges'));
const AdminAbandonedCarts = lazy(() => import('@/components/admin/AdminAbandonedCarts'));
const AdminOrderLocks = lazy(() => import('@/components/admin/AdminOrderLocks'));
const AdminFreeCredits = lazy(() => import('@/components/admin/AdminFreeCredits'));
const AdminExclusiveSpin = lazy(() => import('@/components/admin/AdminExclusiveSpin'));
const AdminReviews = lazy(() => import('@/components/admin/AdminReviews'));
const AdminCatering = lazy(() => import('@/components/admin/AdminCatering'));
const AdminStore = lazy(() => import('@/components/admin/AdminStore'));
const AdminWalletTransactions = lazy(() => import('@/components/admin/AdminWalletTransactions'));
const AdminAcademicCalendar = lazy(() => import('@/components/admin/AdminAcademicCalendar'));
const AdminWebhooks = lazy(() => import('@/components/admin/AdminWebhooks'));
const AdminAmbassadors = lazy(() => import('@/components/admin/AdminAmbassadors'));
const AdminAmbassadorPromo = lazy(() => import('@/components/admin/AdminAmbassadorPromo'));
const AdminAmbassadorReviews = lazy(() => import('@/components/admin/AdminAmbassadorReviews'));
import { isAuthenticated } from '@/lib/apiClient';
import { useCampus } from '@/lib/campusContext';
import { sectionsForRole } from '@/lib/adminSections';

const TITLES = {
  dashboard: 'Dashboard Overview',
  analytics: 'Analytics & Trends',
  economics: 'HP Economics',
  walletanalytics: 'Wallet & Funding',
  users: 'User Management',
  orders: 'Order Management',
  wallet: 'Wallet Transactions',
  delivery: 'Delivery Operations',
  menu: 'Menu Items',
  addons: 'Addons & Variations',
  events: 'Events',
  rewards: 'Rewards & Redemptions',
  marketplace: 'Marketplace',
  promos: 'Promo Code Management',
  abandoned: 'Abandoned Carts',
  orderlocks: 'Order Locks',
  challenges: 'Challenges',
  freecredits: 'Free Side Credits',
  exclusivespin: 'Exclusive Spin Admin',
  hp: 'HP & Multipliers',
  notifications: 'Campaigns & Blasts',
  store: 'Store / Stock Tracking',
  leaderboard: 'Leaderboard & Hall of Fame',
  departments: 'Departments & Academic Levels',
  storefront: 'Storefront Banners',
  reviews: 'Reviews',
  catering: 'Catering Management',
  onboarding: 'Onboarding & Graduation',
  flags: 'Feature Flags',
  settings: 'System Settings',
  academiccalendar: 'Academic Calendar',
  campuses: msg('FE_CAMPUSES', 'Campuses'),
  webhooks: 'Webhook Events',
  system: 'System — Cron & Audit',
  ambassadors: msg('FE_ADMIN_AMBASSADORS_TITLE', 'Campus Ambassadors'),
  ambassadorpromo: msg('FE_ADMIN_AMBASSADOR_PROMO_TITLE', 'Promo Distribution'),
  ambassadorreviews: msg('FE_ADMIN_AMBASSADOR_REVIEWS_TITLE', 'Monthly Reviews'),
};

export default function Admin({ communityWorkspace = false }: { communityWorkspace?: boolean }) {
  const { user, isLoading, logout } = useHolyGrill();
  const [searchParams, setSearchParams] = useSearchParams();
  // A community_manager only carries the three ambassador sections. Their
  // default landing page is the ambassador roster; any other section id in
  // the URL is rewritten before a request can be made.
  const allowedSections = sectionsForRole(user?.role).filter(section => !communityWorkspace || ['ambassadors', 'ambassadorpromo', 'ambassadorreviews'].includes(section.id));
  const allowedIds = new Set(allowedSections.map((s) => s.id));
  const defaultSection = (communityWorkspace || user?.role === 'community_manager') ? 'ambassadors' : 'dashboard';
  const requestedSection = searchParams.get('section') || defaultSection;
  const active = allowedIds.has(requestedSection) ? requestedSection : defaultSection;
  const setActive = (section: string) => {
    if (allowedIds.has(section)) setSearchParams({ section });
  };
  // Campus scope. The header selector writes hg_admin_campus_id, which
  // apiClient sends as X-Campus-ID on the *next* request — but every admin
  // section loads once on mount, so without a remount the tables kept showing
  // the previous campus's data. Keying the content region on the campus id is
  // what makes the switcher actually re-query (and re-render) the panel.
  const { adminCampusId } = useCampus();

  // Check the live token (not a local snapshot) so that a session cleared by
  // HolyGrillContext on profile-fetch failure also redirects to login.
  if (!isAuthenticated()) return <Navigate to="/login" state={{ from: communityWorkspace ? '/community-manager' : '/admin' }} replace />;

  // Wait for the user profile before checking role — the JWT alone proves
  // authentication, but the role comes from /auth/me.
  if (isLoading || !user) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background gap-4">
        <BrandLogo size="md" className="animate-flame-flicker" />
        <div className="w-7 h-7 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Role gate — admin/super_admin plus the restricted community_manager, who
  // only ever reaches the three ambassador sections (filtered above). Every
  // backend route independently re-checks the role, so hiding sections is not
  // the security boundary.
  if (!['admin', 'super_admin', 'community_manager'].includes(user.role)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="text-center max-w-sm">
          <div className="w-14 h-14 rounded-2xl bg-destructive/10 flex items-center justify-center mx-auto mb-4">
            <ShieldAlert className="w-7 h-7 text-destructive" />
          </div>
          <h1 className="font-heading font-extrabold text-xl text-foreground">Access denied</h1>
          <p className="text-sm text-muted-foreground mt-1">Admin rights required.</p>
          <button
            onClick={() => { void logout(); }}
            className="mt-5 inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition"
          >
            <LogOut className="w-3.5 h-3.5" /> Back to login
          </button>
        </div>
      </div>
    );
  }

  const renderSection = () => {
    switch (active) {
      case 'dashboard': return <AdminDashboard />;
      case 'analytics': return <AdminAnalytics />;
      case 'economics': return <AdminEconomics />;
      case 'walletanalytics': return <AdminWalletAnalytics />;
      case 'users': return <AdminUsers />;
      case 'orders': return <AdminOrders />;
      case 'wallet': return <AdminWalletTransactions />;
      case 'delivery': return <AdminDelivery />;
      case 'menu': return <AdminMenu />;
      case 'addons': return <AdminAddons />;
      case 'events': return <AdminEvents />;
      case 'rewards': return <AdminRewards />;
      case 'marketplace': return <AdminMarketplace />;
      case 'promos': return <AdminPromos />;
      case 'challenges': return <AdminChallenges />;
      case 'abandoned': return <AdminAbandonedCarts />;
      case 'orderlocks': return <AdminOrderLocks />;
      case 'freecredits': return <AdminFreeCredits />;
      case 'exclusivespin': return <AdminExclusiveSpin />;
      case 'hp': return <AdminHpMultipliers />;
      case 'notifications': return <AdminNotifications />;
      case 'store': return <AdminStore />;
      case 'leaderboard': return <AdminLeaderboard />;
      case 'departments': return <AdminDepartments />;
      case 'storefront': return <AdminStorefront />;
      case 'reviews': return <AdminReviews />;
      case 'catering': return <AdminCatering />;
      case 'onboarding': return <AdminOnboarding />;
      case 'flags': return <AdminFeatureFlags />;
      case 'settings': return <AdminSystemSettings />;
      case 'academiccalendar': return <AdminAcademicCalendar />;
      case 'campuses': return <AdminCampuses />;
      case 'webhooks': return <AdminWebhooks />;
      case 'system': return <AdminSystem />;
      case 'ambassadors': return <AdminAmbassadors />;
      case 'ambassadorpromo': return <AdminAmbassadorPromo />;
      case 'ambassadorreviews': return <AdminAmbassadorReviews />;
      default: return <AdminDashboard />;
    }
  };

  return (
    <AdminLayout
      active={active}
      onSelect={setActive}
      onNavigate={setActive}
      title={TITLES[active] || 'Admin'}
      subtitle={communityWorkspace || user?.role === 'community_manager' ? msg('FE_CM_WORKSPACE_SUBTITLE', 'Holy Grills · Community Manager') : 'Holy Grills · Admin Panel'}
      allowedIds={allowedIds}
      onSignOut={() => { void logout(); }}
    >
      {/* Remount the section when the campus scope changes so its data is
          re-fetched with the new X-Campus-ID header. */}
      <div key={adminCampusId || 'all-campuses'}><Suspense fallback={<StaffPanelSkeleton />}>{renderSection()}</Suspense></div>
    </AdminLayout>
  );
}
