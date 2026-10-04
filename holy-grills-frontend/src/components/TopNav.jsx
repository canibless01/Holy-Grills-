import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Flame, ShoppingCart, Bell, ChevronDown, ArrowLeftRight } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgress } from '@/lib/hgUtils';
import TierAvatar from '@/components/TierAvatar';
import ProfileMenuContent from '@/components/ProfileMenuContent';
import MobileProfileDrawer from '@/components/MobileProfileDrawer';
import BrandLogo from '@/components/BrandLogo';
import { useScrollNav } from '@/hooks/useScrollNav';

/**
 * Desktop-first top navigation — reconciled to the warm food design system.
 * Left: wordmark · Centre: nav links with animated active indicator ·
 * Right: HP pill, cart, notifications, profile menu with tier card.
 *
 * On phones the account menu opens as a side drawer that sits above the
 * floating tab bar, so nothing in it is ever hidden behind the navigation.
 */
const NAV_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/menu', label: 'Menu' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/orders', label: 'My Orders' },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/rewards', label: 'Rewards' },
];

export default function TopNav() {
  const { user, hpBalance, cartCount, unreadCount, logout } = useHolyGrill();
  const navigate = useNavigate();
  const location = useLocation();
  const visible = useScrollNav();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setDropdownOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const isActive = (to) => (to === '/' ? location.pathname === '/' : location.pathname.startsWith(to));

  const tierInfo = hpBalance ? getTierProgress(hpBalance.hp_earned_120day) : null;
  const hpActive = hpBalance?.active ?? 0;

  const closeMenus = () => { setDropdownOpen(false); setDrawerOpen(false); };

  const handleNavigate = (to) => {
    closeMenus();
    navigate(to);
  };

  const handleProfileClick = () => {
    if (window.matchMedia('(max-width: 767px)').matches) setDrawerOpen(true);
    else setDropdownOpen((v) => !v);
  };

  const handleLogout = async () => {
    closeMenus();
    await logout();
    navigate('/login');
  };

  return (
    <>
    <header className={`sticky top-0 z-40 bg-card/80 backdrop-blur-xl border-b border-border/80 transition-transform duration-300 ease-out ${visible ? 'translate-y-0' : '-translate-y-full'}`}>
      <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Wordmark */}
        <Link to="/" className="flex items-center shrink-0 group">
          <BrandLogo size="nav" className="transition-transform group-hover:scale-105" />
        </Link>

        {/* Centre nav — desktop */}
        <nav className="hidden md:flex items-center gap-0.5 flex-nowrap">
          {NAV_LINKS.map((link) => {
            const active = isActive(link.to);
            return (
              <Link
                key={link.to}
                to={link.to}
                className={`relative whitespace-nowrap px-2.5 lg:px-3.5 py-2 rounded-lg text-[13px] font-semibold transition-colors ${
                  active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {link.label}
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    className="absolute inset-x-2.5 -bottom-px h-[2.5px] rounded-full bg-gradient-cta"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-1.5">
          {/* Return-to-panel button — shown only when a staff member (admin /
              kitchen / rider) is browsing the student site, so they can jump
              back to their own panel without using the back button (which can
              trigger a re-auth/logut). */}
          {user && ['admin', 'super_admin', 'kitchen', 'rider'].includes(user.role) && (
            <button
              onClick={() => navigate({ admin: '/admin', super_admin: '/admin', kitchen: '/kitchen', rider: '/rider' }[user.role])}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-foreground text-background text-xs font-bold hover:opacity-90 active:scale-95 transition-all shrink-0"
              title={`Return to ${user.role === 'super_admin' ? 'Admin' : user.role.charAt(0).toUpperCase() + user.role.slice(1)} Panel`}
            >
              <ArrowLeftRight className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">{user.role === 'super_admin' ? 'Admin' : user.role.charAt(0).toUpperCase() + user.role.slice(1)} Panel</span>
            </button>
          )}

          {/* HP pill — quiet status, only for signed-in users */}
          {user && (
            <button
              onClick={() => navigate('/hp-education')}
              className="hidden sm:flex items-center gap-1.5 pl-2 pr-2 lg:pr-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 hover:bg-primary/20 transition-colors shrink-0"
              title={`${hpActive} Holy Points`}
            >
              <Flame className="w-3.5 h-3.5 text-primary" />
              <span className="hidden lg:inline text-xs font-bold text-primary tabular-nums">{hpActive}</span>
            </button>
          )}

          {/* Cart */}
          <button onClick={() => navigate('/cart')} className="relative min-w-[40px] min-h-[40px] flex items-center justify-center rounded-full hover:bg-muted active:scale-95 transition-all" aria-label="Cart">
            <ShoppingCart className="w-[18px] h-[18px] text-foreground" />
            <AnimatePresence>
              {cartCount > 0 && (
                <motion.span
                  key={cartCount}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: [0, 1.3, 1], opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: 'easeOut' }}
                  className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-card"
                >
                  {cartCount}
                </motion.span>
              )}
            </AnimatePresence>
          </button>

          {/* Notifications */}
          <button onClick={() => navigate('/notifications')} className="relative min-w-[40px] min-h-[40px] flex items-center justify-center rounded-full hover:bg-muted active:scale-95 transition-all" aria-label="Notifications">
            <Bell className="w-[18px] h-[18px] text-foreground" />
            <AnimatePresence>
              {unreadCount > 0 && (
                <motion.span
                  key={unreadCount}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: [0, 1.3, 1], opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: 'easeOut' }}
                  className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-primary text-white text-[10px] font-bold ring-2 ring-card"
                >
                  {unreadCount > 9 ? '9+' : unreadCount}
                </motion.span>
              )}
            </AnimatePresence>
          </button>

          {/* Profile — drawer on phones, dropdown on desktop; Sign In for guests */}
          {user ? (
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={handleProfileClick}
                className="flex items-center gap-1.5 p-1 pr-2 rounded-full hover:bg-muted transition-colors"
                aria-label="Your account"
              >
                <TierAvatar user={user} hpEarned120Day={hpBalance?.hp_earned_120day} size="sm" />
                <ChevronDown className={`hidden md:block w-3.5 h-3.5 text-muted-foreground transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              <AnimatePresence>
                {dropdownOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.98 }}
                    transition={{ duration: 0.15, ease: 'easeOut' }}
                    className="hidden md:block absolute right-0 mt-2 w-80 max-h-[80vh] overflow-y-auto rounded-2xl bg-card shadow-card border border-border"
                  >
                    <ProfileMenuContent
                      user={user}
                      hpBalance={hpBalance}
                      tierInfo={tierInfo}
                      onNavigate={handleNavigate}
                      onLogout={handleLogout}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <button onClick={() => navigate('/login')} className="px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold shadow-glow hover:shadow-lg transition-shadow">Sign In</button>
          )}
        </div>
      </div>
    </header>

    <MobileProfileDrawer
      open={drawerOpen}
      onClose={() => setDrawerOpen(false)}
      user={user}
      hpBalance={hpBalance}
      tierInfo={tierInfo}
      onNavigate={handleNavigate}
      onLogout={handleLogout}
    />
    </>
  );
}