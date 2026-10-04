import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Flame, Wallet as WalletIcon, TrendingUp, Lock, ChevronRight, ShoppingBag, Calendar, Trophy, Users, Clock, Timer } from 'lucide-react';
import { motion } from 'framer-motion';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatNaira, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS, getTierAccent, getTierProgress, getTierProgressGradient, getTierOverallProgress } from '@/lib/hgUtils';
import { orderLockMaxReschedules, referralHp } from '@/lib/appConfig';
import DashboardSkeleton from '@/components/skeletons/DashboardSkeleton';
import CountUp from '@/components/CountUp';
import MascotStandee from '@/components/mascot/MascotStandee';
import FlameMark from '@/components/FlameMark';
import TierIcon from '@/components/TierIcon';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, hpBalance, wallet, streak, refreshStreak } = useHolyGrill();
  const [recentOrders, setRecentOrders] = useState([]);
  const [orderLocks, setOrderLocks] = useState([]);
  const [rank, setRank] = useState(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());

  // Tick every 60s so the order-lock countdown stays live without a reload.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const [orders, locks] = await Promise.all([
          liveApi.orders.list({ limit: 10 }).catch(() => []),
          liveApi.orderLocks.list().catch(() => []),
        ]);
        setRecentOrders(Array.isArray(orders) ? orders : []);
        setOrderLocks(Array.isArray(locks) ? locks : []);
        refreshStreak();
        try { const r = await liveApi.leaderboard.getMyRank(); setRank(r); } catch { /* ignore */ }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const hpActive = hpBalance?.active || 0;
  const streakDays = streak?.streak_count ?? streak?.current_streak ?? streak?.days ?? streak?.count ?? 0;
  // Backend's authoritative weekly calendar (GET /auth/streak → week_progress).
  // The login-streak week is Mon–Sun (ISO); each day is checked / reclaimed /
  // missed / today / upcoming. Mirrors the Streak page so the flames reflect the
  // days you actually logged in — not a rolling 7-day cycle.
  const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const weekDaysMap = streak?.week_progress?.days || {};
  const weekStrip = WEEKDAYS.map((d) => ({ day: d, status: weekDaysMap[d] || 'upcoming' }));
  const isDone = (st) => st === 'checked' || st === 'checked_in' || st === 'reclaimed';
  const completedThisWeek = weekStrip.filter((d) => isDone(d.status)).length;
  const missedThisWeek = weekStrip.filter((d) => d.status === 'missed').length;
  const remainingThisWeek = weekStrip.filter((d) => d.status === 'today' || d.status === 'upcoming').length;
  const weeklyOrders = streak?.weekly_order_count ?? streak?.order_streak ?? 0;
  const orderStreakWeeks = streak?.consecutive_weeks ?? streak?.order_streak_weeks ?? weeklyOrders ?? 0;
  const myRank = rank?.rank ?? '—';
  // GET /hp/balance returns this at the top level, exact name. No fallbacks —
  // they only ever masked the real value as 0 and froze the tier ring.
  const hpForTier = hpBalance?.hp_earned_120day ?? 0;
  const accent = getTierAccent(hpForTier);
  const tierProgress = getTierProgress(hpForTier);
  const tierGradient = getTierProgressGradient(hpForTier);
  // Continuous fill across the whole ladder — never resets when a tier unlocks.
  const tierOverall = getTierOverallProgress(hpForTier);
  const inGrace = hpBalance?.is_in_grace_period || hpBalance?.tier?.is_in_grace_period;
  const graceEndsAt = hpBalance?.grace_period_ends_at || hpBalance?.tier?.grace_period_ends_at;
  const activeLocks = orderLocks.filter(l => (l.status || 'active') === 'active' && !l.consumed_at);
  const maxReschedules = orderLockMaxReschedules();

  // Order Lock prompt — appears only after you place an order, with a 24h
  // countdown from the order's placed time. If you don't lock in within 24h it
  // disappears; once you set a lock it shows as an active lock instead. One
  // active lock per session is enforced by the backend.
  const eligibleOrders = recentOrders.filter(o => !['cancelled', 'refunded'].includes(o.status));
  const latestOrder = eligibleOrders.length
    ? eligibleOrders.reduce((a, b) => new Date(b.created_date || b.created_at) > new Date(a.created_date || a.created_at) ? b : a)
    : null;
  const orderPlacedAt = latestOrder ? new Date(latestOrder.created_date || latestOrder.created_at) : null;
  const msSinceOrder = orderPlacedAt ? now - orderPlacedAt.getTime() : null;
  const within24h = msSinceOrder !== null && msSinceOrder < 24 * 60 * 60 * 1000;
  const showLockPrompt = !activeLocks.length && latestOrder && within24h;
  const hoursLeft = showLockPrompt ? Math.max(0, 24 - Math.floor(msSinceOrder / (60 * 60 * 1000))) : 0;

  const statTiles = [
    { label: 'HP Balance', value: hpActive, icon: Flame, bg: 'bg-accent/10', iconBg: 'bg-primary/10', iconColor: 'text-primary', to: '/hp-education' },
    { label: 'Wallet', value: wallet?.balance || 0, format: (v) => formatNaira(v), icon: WalletIcon, bg: 'bg-success/10', iconBg: 'bg-success/15', iconColor: 'text-success', to: '/wallet' },
  ];

  const quickActions = [
    { label: 'Events', subtitle: 'Earn HP', icon: Calendar, to: '/events', bg: 'bg-brand-brown' },
    { label: 'Marketplace', subtitle: 'Browse deals', icon: ShoppingBag, to: '/marketplace', bg: 'bg-accent' },
    { label: 'Leaderboard', subtitle: `Rank #${myRank}`, icon: Trophy, to: '/leaderboard', bg: 'bg-primary', span: 'col-span-2 sm:col-span-1' },
  ];

  if (loading) return <DashboardSkeleton />;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Greeting */}
      <div>
        <h1 className="font-heading font-extrabold text-2xl text-foreground flex items-center gap-1.5">Welcome back <TierIcon slug={accent.slug} className="w-5 h-5 text-lg" /></h1>
      </div>

      {/* Login streak — auto/system-read, no button. Aligned to the backend's
          Mon–Sun week_progress so the flames reflect the days you actually logged in. */}
      <div className="rounded-2xl p-4 text-white relative overflow-hidden shadow-glow" style={{ background: tierGradient }}>
        <FlameMark className="absolute -right-4 -top-4 w-24 h-24 opacity-15" />
        <div className="relative">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
                <Flame className="w-4 h-4 text-white animate-flame-flicker" />
              </div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-white/80">Login Streak</div>
            </div>
            <div className="text-[10px] text-white/60">{completedThisWeek}/7 this week{missedThisWeek > 0 ? ` · ${missedThisWeek} missed` : ''}</div>
          </div>
          <motion.div
            key={streakDays}
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 200 }}
            className="font-heading font-extrabold text-3xl text-white"
          >
            <CountUp value={streakDays} /> <span className="text-sm font-normal text-white/80">day streak</span>
          </motion.div>
          {/* 7-day Mon–Sun strip — lit for days you actually checked in or reclaimed. */}
          <div className="flex justify-between gap-1 mt-3">
            {weekStrip.map((d, i) => (
              <div key={i} className="flex flex-col items-center gap-0.5">
                <Flame className={`w-4 h-4 ${isDone(d.status) ? 'text-white' : 'text-white/25'}`} />
                <span className="text-[8px] text-white/50">{['M','T','W','T','F','S','S'][i]}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 text-center text-[10px] text-white/70 leading-relaxed">
            {completedThisWeek >= 7
              ? 'Week complete. HP on the way to your pending balance.'
              : remainingThisWeek > 0
                ? `Log in ${remainingThisWeek} more day${remainingThisWeek === 1 ? '' : 's'} this week to complete it.`
                : "This week's streak lapsed. A new week starts Monday."}
          </div>
          <Link to="/streak" className="block text-center mt-2 text-[10px] font-bold text-white/80 hover:text-white underline">View streak calendar →</Link>
        </div>
      </div>

      {/* HP tier progress — progression to the next level */}
      <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <TrendingUp className="w-4 h-4 text-primary" />
            </div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">HP Progress</div>
          </div>
        </div>
        <div className="mt-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">{tierProgress?.next ? `${tierProgress.current.name} → ${tierProgress.next.name}` : `${tierProgress?.current?.name ?? 'Tier'} · max tier`}</span>
            {tierProgress?.next && <span className="text-[10px] font-bold text-primary">{tierProgress.remaining} HP to next tier</span>}
          </div>
          {/* Continuous fill — climbs from the first tier to the last, never
              emptying out when a new tier unlocks. Inherits the tier gradient. */}
          <div className="h-2 rounded-full bg-secondary overflow-hidden">
            <div className="h-full rounded-full transition-all duration-700 ease-out" style={{ width: `${tierOverall.progress}%`, background: tierGradient }} />
          </div>
        </div>
        {inGrace && (
          <div className="mt-3 flex items-center gap-2 p-2.5 rounded-xl bg-accent/10 border border-accent/20">
            <Clock className="w-4 h-4 text-accent shrink-0" />
            <div className="text-[11px] text-accent font-semibold">
              Tier grace period active{graceEndsAt ? ` · ends ${new Date(graceEndsAt).toLocaleDateString()}` : ''}. Earn HP to keep your tier.
            </div>
          </div>
        )}
      </div>

      {/* Stat grid */}
      <div className="grid grid-cols-2 gap-3">
        {statTiles.map(tile => (
          <Link key={tile.label} to={tile.to} className={`rounded-2xl ${tile.bg} border border-border p-4 hover:shadow-md transition-all relative`}>
            <ChevronRight className="w-4 h-4 text-foreground/30 absolute top-3 right-3" />
            <div className={`w-9 h-9 rounded-full ${tile.iconBg} flex items-center justify-center mb-2`}>
              <tile.icon className={`w-5 h-5 ${tile.iconColor}`} />
            </div>
            <div className="font-heading font-extrabold text-lg text-foreground">{tile.format ? <CountUp value={tile.value} format={tile.format} /> : <CountUp value={tile.value} />}</div>
            <div className="text-xs text-muted-foreground font-medium">{tile.label}</div>
          </Link>
        ))}
      </div>

      {/* Active order locks */}
      {activeLocks.map(lock => {
        const lockedDate = lock.locked_date ? new Date(lock.locked_date) : null;
        const daysToLock = lockedDate ? Math.ceil((lockedDate.getTime() - now) / (24 * 60 * 60 * 1000)) : null;
        const isHp = (lock.reward_type || lock.reward) === 'hp';
        const reschedulesLeft = maxReschedules - (lock.reschedule_count || 0);
        return (
          <Link key={lock.id} to="/order-locks" className="block rounded-2xl bg-accent/10 border border-primary/20 p-4 hover:shadow-md transition-all">
            <div className="flex items-center gap-3">
              <Lock className="w-5 h-5 text-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground">
                  {isHp ? `${lock.reward_hp_amount || 0} HP reward locked` : `${lock.discount_pct || 0}% off locked`}
                  {reschedulesLeft > 0 && <span className="ml-1 text-[10px] font-normal text-muted-foreground">· {reschedulesLeft} reschedule{reschedulesLeft !== 1 ? 's' : ''} left</span>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {lockedDate ? `Order on ${lockedDate.toLocaleDateString()} to claim · ${daysToLock > 0 ? `${daysToLock} day${daysToLock !== 1 ? 's' : ''} to go` : 'today!'}` : 'Tap to view'}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-primary shrink-0" />
            </div>
          </Link>
        );
      })}

      {/* Lock-in prompt — order placed, no active lock, within 24h */}
      {showLockPrompt && (
        <Link to="/order-locks" className="block rounded-2xl bg-gradient-cta p-4 text-white hover:scale-[1.01] transition-transform shadow-glow">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
              <Lock className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-heading font-bold text-sm text-white">Lock in your next order!</div>
              <div className="text-xs text-white/85 mt-0.5">You just placed an order. Lock in your next date within 24h to claim a reward or discount.</div>
            </div>
            <div className="text-right shrink-0">
              <div className="flex items-center gap-1 text-[10px] font-bold text-white/90">
                <Timer className="w-3 h-3" />
                {hoursLeft}h left
              </div>
              <div className="text-[9px] text-white/60">to lock in</div>
            </div>
          </div>
        </Link>
      )}

      {/* Recent Orders */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-heading font-bold text-lg text-foreground">Recent Orders</h2>
          <Link to="/orders" className={`text-xs font-bold ${accent.text}`}>See all →</Link>
        </div>
        {recentOrders.length === 0 ? (
          <div className="rounded-2xl bg-card border border-border p-6 text-center">
            <MascotStandee mascot="waving" className="w-24 h-24 mx-auto mb-1" alt="No orders yet" />
            <p className="text-sm text-muted-foreground">No orders yet</p>
            <button onClick={() => navigate('/menu')} className="mt-2 text-xs font-bold text-primary">Start ordering →</button>
          </div>
        ) : (
          <div className="space-y-2">
            {recentOrders.map(order => (
              <Link key={order.id} to={`/orders/${order.id}`} className="block rounded-2xl bg-card border border-border p-3 hover:shadow-md transition-all">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${ORDER_STATUS_COLORS[order.status] || 'bg-secondary text-foreground'}`}>
                        {ORDER_STATUS_LABELS[order.status] || order.status}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{new Date(order.created_date || order.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="text-sm text-foreground mt-1 truncate font-medium">
                      {order.order_items?.[0]?.quantity || 1}× {order.order_items?.[0]?.name_snapshot || order.order_items?.[0]?.name || 'Item'}
                      {order.order_items?.length > 1 && ` +${order.order_items.length - 1} more`}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="font-bold text-primary text-sm whitespace-nowrap">{formatNaira(order.total_amount || order.total || 0)}</span>
                    <ChevronRight className="w-4 h-4 text-foreground/30" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Order streak — weeks of consistency */}
      <div className={`rounded-2xl ${accent.light} border ${accent.lightBorder} p-4`}>
        <div className="flex items-center gap-2 mb-2">
          <Flame className={`w-4 h-4 ${accent.text} shrink-0`} />
          <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Order Streak</span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-heading font-extrabold text-2xl text-foreground tabular-nums"><CountUp value={orderStreakWeeks} /></span>
          <span className="text-xs text-muted-foreground">week{orderStreakWeeks !== 1 ? 's' : ''} of consistency</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {orderStreakWeeks > 0 ? 'Order this week to keep your streak alive' : 'Place an order this week to start your order streak'}
        </p>
      </div>

      {/* Quick-action grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {quickActions.map(a => (
          <Link key={a.label} to={a.to} className={`relative rounded-2xl ${a.bg} ${a.span || ''} p-4 flex flex-col gap-2 hover:scale-[1.02] transition-transform`}>
            <a.icon className="w-6 h-6 text-white" />
            <div className="font-heading font-bold text-base text-white">{a.label}</div>
            <div className="text-xs text-white/80">{a.subtitle}</div>
            <ChevronRight className="absolute top-3 right-3 w-4 h-4 text-white/70" />
          </Link>
        ))}
      </div>

      {/* Referral Wins */}
      <Link to="/referrals" className="block rounded-2xl bg-card border border-border p-4 hover:shadow-md transition-all">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-accent/15 flex items-center justify-center">
            <Users className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1">
            <div className="font-bold text-sm text-foreground">Referral Wins</div>
            <div className="text-xs text-muted-foreground">{referralHp()} HP per referral · Invite friends to earn</div>
          </div>
          <ChevronRight className="w-5 h-5 text-foreground/30" />
        </div>
      </Link>
    </div>
  );
}