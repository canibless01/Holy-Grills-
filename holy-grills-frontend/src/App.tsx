import { lazy, Suspense } from 'react';
import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import ScrollToTop from './components/ScrollToTop';
import { HolyGrillProvider } from '@/lib/HolyGrillContext';
import { CampusProvider } from '@/lib/campusContext';
import Layout from '@/components/Layout';
import CampusScope from '@/components/CampusScope';
import InstallPrompt from '@/components/InstallPrompt';
import CookieConsent from '@/components/CookieConsent';
import RequireAuth from '@/components/RequireAuth';
import { SoundProvider } from '@/lib/SoundProvider';
import ErrorBoundary from '@/components/ErrorBoundary';

// Eager imports — the entry-critical screens render with no per-route
// Suspense spinner. Everything else is split at the route (see below).
import Home from '@/pages/Home';
const Kitchen = lazy(() => import('@/pages/Kitchen'));
const Rider = lazy(() => import('@/pages/Rider'));
const Admin = lazy(() => import('@/pages/Admin'));
import Login from '@/pages/Login';
import Register from '@/pages/Register';

// Route-level code splitting — each non-entry page loads on first visit,
// which keeps the initial JS to the landing/auth screens instead of the
// whole app. <Suspense> below renders the app skeleton during the fetch.
const Menu = lazy(() => import('@/pages/Menu'));
const ItemDetail = lazy(() => import('@/pages/ItemDetail'));
const Cart = lazy(() => import('@/pages/Cart'));
const Checkout = lazy(() => import('@/pages/Checkout'));
const OrderConfirmation = lazy(() => import('@/pages/OrderConfirmation'));
const Orders = lazy(() => import('@/pages/Orders'));
const OrderDetail = lazy(() => import('@/pages/OrderDetail'));
const TrackOrders = lazy(() => import('@/pages/TrackOrders'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const HpEducation = lazy(() => import('@/pages/HpEducation'));
const Rewards = lazy(() => import('@/pages/Rewards'));
const Leaderboard = lazy(() => import('@/pages/Leaderboard'));
const Wallet = lazy(() => import('@/pages/Wallet'));
const Marketplace = lazy(() => import('@/pages/Marketplace'));
const MarketplaceDetail = lazy(() => import('@/pages/MarketplaceDetail'));
const Events = lazy(() => import('@/pages/Events'));
const EventDetail = lazy(() => import('@/pages/EventDetail'));
const TierDetail = lazy(() => import('@/pages/TierDetail'));
const Profile = lazy(() => import('@/pages/Profile'));
const Addresses = lazy(() => import('@/pages/Addresses'));
const NotificationPreferences = lazy(() => import('@/pages/NotificationPreferences'));
const Notifications = lazy(() => import('@/pages/Notifications'));
const Referrals = lazy(() => import('@/pages/Referrals'));
const OrderLocks = lazy(() => import('@/pages/OrderLocks'));
const Squads = lazy(() => import('@/pages/Squads'));
const Streak = lazy(() => import('@/pages/Streak'));
const HallOfFame = lazy(() => import('@/pages/HallOfFame'));
const FAQ = lazy(() => import('@/pages/FAQ'));
const TermsPrivacy = lazy(() => import('@/pages/TermsPrivacy'));
const OurStory = lazy(() => import('@/pages/OurStory'));
const ForgotPassword = lazy(() => import('@/pages/ForgotPassword'));
const ResetPassword = lazy(() => import('@/pages/ResetPassword'));
const OAuthConsent = lazy(() => import('@/pages/OAuthConsent'));

const AppRoutes = () => {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-background"><div className="w-10 h-10 rounded-xl bg-muted animate-pulse" /></div>}>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/mcp-consent" element={<OAuthConsent />} />
      <Route element={<Layout />}>
        {/* Public browsing + ordering (guests welcome) */}
        <Route path="/" element={<Home />} />
        {/* Domain 0 — campus-scoped routes. Guests get the non-cancelable
            CampusGate before these; authenticated users are scoped by their
            own campus_id. Static pages (FAQ, Terms, Our Story) stay open. */}
        <Route element={<CampusScope />}>
          <Route path="/menu" element={<Menu />} />
          <Route path="/menu/:id" element={<ItemDetail />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/events" element={<Events />} />
          <Route path="/events/tiers/:tierId" element={<TierDetail />} />
          <Route path="/events/:id" element={<EventDetail />} />
          <Route path="/marketplace" element={<Marketplace />} />
          <Route path="/marketplace/:id" element={<MarketplaceDetail />} />
        </Route>
        <Route path="/order-confirmation/:id" element={<OrderConfirmation />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:id" element={<OrderDetail />} />
        <Route path="/track-orders" element={<TrackOrders />} />
        <Route path="/faq" element={<FAQ />} />
        <Route path="/terms" element={<TermsPrivacy />} />
        <Route path="/our-story" element={<OurStory />} />
        {/* Authenticated student routes */}
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/hp-education" element={<HpEducation />} />
          <Route path="/rewards" element={<Rewards />} />
          <Route path="/wallet" element={<Wallet />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/addresses" element={<Addresses />} />
          <Route path="/notification-preferences" element={<NotificationPreferences />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/referrals" element={<Referrals />} />
          <Route path="/order-locks" element={<OrderLocks />} />
          <Route path="/squads" element={<Squads />} />
          <Route path="/streak" element={<Streak />} />
          <Route path="/hall-of-fame" element={<HallOfFame />} />
        </Route>
      </Route>
      <Route path="/admin" element={<Admin />} />
      <Route path="/kitchen" element={<Kitchen />} />
      <Route path="/rider" element={<Rider />} />
      <Route path="*" element={<PageNotFound />} />
    </Routes>
    </Suspense>
  );
};

function App() {
  return (
    <ErrorBoundary>
        <QueryClientProvider client={queryClientInstance}>
          <Router>
            <ScrollToTop />
            <SoundProvider>
              <HolyGrillProvider>
                <CampusProvider>
                  <AppRoutes />
                </CampusProvider>
                <InstallPrompt />
                <CookieConsent />
              </HolyGrillProvider>
            </SoundProvider>
          </Router>
          <Toaster />
        </QueryClientProvider>
    </ErrorBoundary>
  )
}

export default App