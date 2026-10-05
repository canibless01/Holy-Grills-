import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, ExternalLink, LogOut, UtensilsCrossed, Bike, Search, X } from 'lucide-react';
import AdminGlobalSearch from '@/components/admin/AdminGlobalSearch';
import AdminCampusSelector from '@/components/admin/AdminCampusSelector';
import InlineNotificationBell from '@/components/InlineNotificationBell';
import BrandLogo from '@/components/BrandLogo';

/**
 * Admin top bar — compact, glassy, responsive.
 *
 * Desktop:  [title + subtitle] [global search] [campus] [bell] [Kitchen] [Rider] [View Site] [Sign out]
 * Mobile:   [hamburger] [title] [campus] [search toggle] [bell] [sign out]
 *           + a full-width search row that expands under the header.
 *
 * The global search jumps to any admin section (type "multiplier" → HP &
 * Multipliers) and matches live records — available on BOTH mobile and desktop.
 * Title/subtitle come from the TITLES map in Admin.tsx.
 */
export default function AdminHeader({ title, subtitle, onOpenMobile, onSignOut, onNavigate }) {
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 bg-card/90 backdrop-blur-md border-b border-border">
      <div className="px-4 lg:px-8 h-14 flex items-center justify-between gap-3">
        {/* Left — mobile menu + title */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onOpenMobile}
            className="lg:hidden p-2 -ml-1 rounded-xl hover:bg-secondary active:scale-95 transition shrink-0"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5 text-foreground" />
          </button>
          <div className="flex items-center gap-2.5 min-w-0">
            {/* Logo is desktop-only — mobile needs the room for the action icons. */}
            <BrandLogo size="admin" className="hidden lg:block shrink-0" />
            <div className="min-w-0 leading-tight">
              <h1 className="font-heading font-extrabold text-sm sm:text-base text-foreground truncate">{title}</h1>
              {subtitle && (
                <p className="text-[10px] sm:text-[11px] text-muted-foreground font-bold uppercase tracking-wide truncate">{subtitle}</p>
              )}
            </div>
          </div>
        </div>

        {/* Center — global search (desktop) */}
        <div className="hidden lg:block flex-1 max-w-sm">
          <AdminGlobalSearch onNavigate={onNavigate} />
        </div>

        {/* Right — campus + actions */}
        <div className="flex items-center gap-1 shrink-0">
          <AdminCampusSelector />
          {/* Mobile search toggle */}
          <button
            onClick={() => setSearchOpen((v) => !v)}
            className={`lg:hidden w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
              searchOpen ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-primary hover:bg-primary/10'
            }`}
            aria-label="Search admin panel"
          >
            {searchOpen ? <X className="w-4 h-4" /> : <Search className="w-4 h-4" />}
          </button>
          <InlineNotificationBell />
          <Link
            to="/kitchen"
            aria-label="Kitchen panel"
            title="Kitchen panel"
            className="hidden sm:flex items-center gap-1.5 px-2 lg:px-3 py-1.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-primary hover:bg-primary/10 active:scale-95 transition"
          >
            <UtensilsCrossed className="w-4 h-4" /> <span className="hidden lg:inline">Kitchen</span>
          </Link>
          <Link
            to="/rider"
            aria-label="Rider panel"
            title="Rider panel"
            className="hidden sm:flex items-center gap-1.5 px-2 lg:px-3 py-1.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-primary hover:bg-primary/10 active:scale-95 transition"
          >
            <Bike className="w-4 h-4" /> <span className="hidden lg:inline">Rider</span>
          </Link>
          <Link
            to="/"
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-primary hover:bg-primary/10 active:scale-95 transition"
          >
            View Site <ExternalLink className="w-3 h-3" />
          </Link>
          <button
            onClick={onSignOut}
            className="flex items-center gap-1.5 px-2.5 lg:px-3 py-1.5 rounded-xl text-xs font-bold text-muted-foreground hover:text-destructive hover:bg-destructive/10 active:scale-95 transition"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden lg:inline">Sign out</span>
          </button>
        </div>
      </div>

      {/* Mobile search row — same engine as desktop, full width */}
      {searchOpen && (
        <div className="lg:hidden px-4 pb-3 border-t border-border/60">
          <AdminGlobalSearch onNavigate={onNavigate} />
        </div>
      )}
    </header>
  );
}