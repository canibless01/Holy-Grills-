import { Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, Menu, LayoutDashboard, ClipboardList, Award } from 'lucide-react';
import { useScrollNav } from '@/hooks/useScrollNav';

const navItems = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/menu', label: 'Menu', icon: Menu },
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/orders', label: 'Orders', icon: ClipboardList },
  { to: '/rewards', label: 'Rewards', icon: Award },
];

/**
 * Mobile tab bar — detached "floating" pill that hovers above the page
 * instead of being welded to the bottom edge. The active tab lifts into a
 * soft brand-tinted pill so the current page is readable at a glance.
 *
 * The outer nav is pointer-events-none so the transparent strip around the
 * bar never swallows taps; only the pill itself is interactive.
 */
export default function BottomNav() {
  const location = useLocation();
  const currentPath = location.pathname;
  const visible = useScrollNav();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 md:hidden pb-safe pointer-events-none">
      <div className={`pointer-events-auto mx-3 mb-3 flex items-center justify-between gap-1 rounded-[26px] border border-border/70 bg-card/95 px-2 py-1.5 backdrop-blur-xl shadow-[0_14px_38px_-12px_rgba(31,10,0,0.38)] transition-transform duration-300 ease-out ${visible ? 'translate-y-0' : 'translate-y-[150%]'}`}>
        {navItems.map((item) => {
          const isActive = currentPath === item.to || (item.to !== '/' && currentPath.startsWith(item.to));
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-current={isActive ? 'page' : undefined}
              className="flex-1 flex flex-col items-center justify-center gap-1 py-1 rounded-2xl transition-transform duration-200 active:scale-95"
            >
              <span
                className={`relative flex items-center justify-center w-11 h-8 rounded-full transition-colors duration-300 ${
                  isActive ? 'text-primary' : 'text-muted-foreground'
                }`}
              >
                {isActive && (
                  <motion.span
                    layoutId="bottomnav-active-pill"
                    className="absolute inset-0 rounded-full bg-primary/10"
                    transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                  />
                )}
                <Icon className="w-[19px] h-[19px] relative" strokeWidth={isActive ? 2.6 : 2} />
              </span>
              <span className="flex items-center gap-1">
                {isActive && (
                  <motion.span layoutId="bottomnav-active-flame" className="w-1 h-1 rounded-full bg-primary" transition={{ type: 'spring', stiffness: 420, damping: 32 }} />
                )}
                <span className={`text-[10px] tracking-tight transition-colors ${isActive ? 'text-primary font-extrabold' : 'text-muted-foreground font-semibold'}`}>
                  {item.label}
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}