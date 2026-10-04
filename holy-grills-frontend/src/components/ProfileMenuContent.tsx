import React from 'react';
import { useLocation } from 'react-router-dom';
import {
  Flame, Wallet, Gift, CalendarCheck, Users, Store, Ticket, UserCog, BellRing,
  BookOpen, HelpCircle, FileText, LogOut, X,
} from 'lucide-react';
import TierIcon from '@/components/TierIcon';
import TierAvatar from '@/components/TierAvatar';
import type { getTierProgress } from '@/lib/hgUtils';
import type { AuthUser } from '@/types/auth';
import type { HpBalance } from '@/types/hp';

/**
 * ProfileMenuContent — the account menu body, shared by the desktop dropdown
 * and the mobile side drawer so the two can never drift apart.
 *
 * Structure:
 *  1. Top profile block — brand background, avatar wrapped in its tier ring,
 *     bold name, lighter email, tier badge in the top-right corner, plus the
 *     member's progress toward the next tier.
 *  2. Navigation list — one row per destination, icon left, label right,
 *     generous padding, and a rounded highlight on the current page.
 *  3. Log out, set apart by a rule.
 */
// Destinations NOT already reachable from the top nav or the floating tab bar
// (Home, Menu, Dashboard, My Orders, Rewards, Leaderboard are all there) plus
// the static pages, so the drawer stays short on small screens.
const ITEMS = [
  { to: '/hp-education', label: 'Holy Points', icon: Flame },
  { to: '/wallet', label: 'Wallet', icon: Wallet },
  { to: '/referrals', label: 'Referrals', icon: Gift },
  { to: '/streak', label: 'Streak', icon: CalendarCheck },
  { to: '/squads', label: 'Squads', icon: Users },
  { to: '/marketplace', label: 'Marketplace', icon: Store },
  { to: '/events', label: 'Events', icon: Ticket },
  { to: '/profile', label: 'Profile & Settings', icon: UserCog },
  { to: '/notification-preferences', label: 'Notification Preferences', icon: BellRing },
  { to: '/our-story', label: 'Our Story', icon: BookOpen },
  { to: '/faq', label: 'FAQ', icon: HelpCircle },
  { to: '/terms', label: 'Terms & Privacy', icon: FileText },
];

export default function ProfileMenuContent({
  user,
  hpBalance,
  tierInfo,
  onNavigate,
  onLogout,
  onClose,
}: {
  user?: AuthUser | null;
  hpBalance?: HpBalance | null;
  tierInfo?: ReturnType<typeof getTierProgress> | null;
  onNavigate?: (to: string) => void;
  onLogout?: () => void | Promise<void>;
  /** Optional: the mobile drawer passes it, the desktop dropdown does not. */
  onClose?: () => void;
}) {
  const location = useLocation();

  const isActive = (item) =>
    item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to);

  return (
    <div className="flex flex-col">
      {/* ── Top profile area ── */}
      <div className="bg-gradient-dark px-5 pt-5 pb-4 text-white">
        <div className="flex items-start gap-3.5">
          <TierAvatar user={user} hpEarned120Day={hpBalance?.hp_earned_120day} size="lg" />

          <div className="min-w-0 flex-1 pt-0.5">
            <div className="font-heading font-extrabold text-lg leading-tight truncate">
              {user?.full_name || 'Your account'}
            </div>
            <div className="text-xs text-white/65 truncate mt-1">{user?.email}</div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {tierInfo?.current && (
              <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-white/15 border border-white/25">
                <TierIcon slug={tierInfo.current.slug} tier={tierInfo.current} className="w-3.5 h-3.5 text-[11px] leading-none" />
                <span className="text-[10px] font-bold uppercase tracking-wider">{tierInfo.current.name}</span>
              </span>
            )}
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close menu"
                className="p-1.5 rounded-full hover:bg-white/20 active:scale-95 transition"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {tierInfo?.next && (
          <div className="mt-4">
            <div className="h-1.5 rounded-full bg-black/25 overflow-hidden">
              <div className="h-full rounded-full bg-gradient-cta" style={{ width: `${tierInfo.progress}%` }} />
            </div>
            <div className="text-[10px] font-semibold text-white/70 mt-1.5">
              {tierInfo.remaining} HP to {tierInfo.next.name}
            </div>
          </div>
        )}
      </div>

      {/* ── Navigation list ── */}
      <nav className="px-2 py-2">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isActive(item);
          return (
            <button
              key={item.to}
              type="button"
              onClick={() => onNavigate(item.to)}
              className={`flex w-full items-center gap-4 px-4 py-3 rounded-xl text-left text-sm transition-colors ${
                active ? 'bg-primary/10 text-primary font-extrabold' : 'text-foreground font-semibold hover:bg-muted'
              }`}
            >
              <Icon className={`w-5 h-5 shrink-0 ${active ? 'text-primary' : 'text-muted-foreground'}`} />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="px-2 pb-2">
        <div className="border-t border-border pt-2">
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-4 px-4 py-3 rounded-xl text-left text-sm font-bold text-destructive hover:bg-destructive/10 transition-colors"
          >
            <LogOut className="w-5 h-5 shrink-0" /> Log out
          </button>
        </div>
      </div>
    </div>
  );
}