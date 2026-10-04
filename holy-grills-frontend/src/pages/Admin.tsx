import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { ShieldAlert, LogOut } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import BrandLogo from '@/components/BrandLogo';
import AdminLayout from '@/components/admin/AdminLayout';
import AdminDashboard from '@/components/admin/AdminDashboard';
import AdminAnalytics from '@/components/admin/AdminAnalytics';
import AdminEconomics from '@/components/admin/AdminEconomics';
import AdminUsers from '@/components/admin/AdminUsers';
import AdminOrders from '@/components/admin/AdminOrders';
import AdminDelivery from '@/components/admin/AdminDelivery';
import AdminPromos from '@/components/admin/AdminPromos';
import AdminFeatureFlags from '@/components/admin/AdminFeatureFlags';
import AdminSystemSettings from '@/components/admin/AdminSystemSettings';
import AdminSystem from '@/components/admin/AdminSystem';
import AdminMenu from '@/components/admin/AdminMenu';
import AdminAddons from '@/components/admin/AdminAddons';
import AdminEvents from '@/components/admin/AdminEvents';
import AdminRewards from '@/components/admin/AdminRewards';
import AdminMarketplace from '@/components/admin/AdminMarketplace';
import AdminNotifications from '@/components/admin/AdminNotifications';
import AdminLeaderboard from '@/components/admin/AdminLeaderboard';
import AdminDepartments from '@/components/admin/AdminDepartments';
import AdminStorefront from '@/components/admin/AdminStorefront';
import AdminOnboarding from '@/components/admin/AdminOnboarding';
import AdminHpMultipliers from '@/components/admin/AdminHpMultipliers';
import AdminChallenges from '@/components/admin/AdminChallenges';
import AdminAbandonedCarts from '@/components/admin/AdminAbandonedCarts';
import AdminOrderLocks from '@/components/admin/AdminOrderLocks';
import AdminFreeCredits from '@/components/admin/AdminFreeCredits';
import AdminExclusiveSpin from '@/components/admin/AdminExclusiveSpin';
import AdminReviews from '@/components/admin/AdminReviews';
import AdminCatering from '@/components/admin/AdminCatering';
import AdminStore from '@/components/admin/AdminStore';
import AdminWalletTransactions from '@/components/admin/AdminWalletTransactions';
import AdminAcademicCalendar from '@/components/admin/AdminAcademicCalendar';
import AdminWebhooks from '@/components/admin/AdminWebhooks';
import { isAuthenticated, clearTokens } from '@/lib/apiClient';

const TITLES = {
  dashboard: 'Dashboard Overview',
  analytics: 'Analytics & Trends',
  economics: 'HP Economics',
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
  webhooks: 'Webhook Events',
  system: 'System — Cron & Audit',
};

export default function Admin() {
  const { user, isLoading } = useHolyGrill();
  const navigate = useNavigate();
  const [active, setActive] = useState('dashboard');

  // Check the live token (not a local snapshot) so that a session cleared by
  // HolyGrillContext on profile-fetch failure also redirects to login.
  if (!isAuthenticated()) return <Navigate to="/login" state={{ from: '/admin' }} replace />;

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

  // Role gate — admin and super_admin only. Everything else a backend accepts
  // from a regular campus admin stays open to both roles here (the backend
  // scope-checks per campus anyway).
  if (!['admin', 'super_admin'].includes(user.role)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="text-center max-w-sm">
          <div className="w-14 h-14 rounded-2xl bg-destructive/10 flex items-center justify-center mx-auto mb-4">
            <ShieldAlert className="w-7 h-7 text-destructive" />
          </div>
          <h1 className="font-heading font-extrabold text-xl text-foreground">Access denied</h1>
          <p className="text-sm text-muted-foreground mt-1">Admin rights required.</p>
          <button
            onClick={() => { clearTokens(); navigate('/login', { replace: true }); }}
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
      case 'webhooks': return <AdminWebhooks />;
      case 'system': return <AdminSystem />;
      default: return <AdminDashboard />;
    }
  };

  return (
    <AdminLayout
      active={active}
      onSelect={setActive}
      onNavigate={setActive}
      title={TITLES[active] || 'Admin'}
      subtitle="Holy Grills · Admin Panel"
      onSignOut={() => {
        clearTokens();
        localStorage.removeItem('hg_admin_campus_id');
        navigate('/login', { replace: true });
      }}
    >
      {renderSection()}
    </AdminLayout>
  );
}