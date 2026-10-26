import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, RotateCcw } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgressGradient } from '@/lib/hgUtils';
import StreakSkeleton from '@/components/skeletons/StreakSkeleton';
import StreakHero from '@/components/streak/StreakHero';
import StreakWeekCalendar from '@/components/streak/StreakWeekCalendar';
import OrderStreakCard from '@/components/streak/OrderStreakCard';
import { msg, useMessages } from '@/lib/messages';
const WEEK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function Streak() {
  useMessages();
  const { streak, refreshStreak, hpBalance } = useHolyGrill();
  const [checkinHistory, setCheckinHistory] = useState([]);
  useEffect(() => {
    void refreshStreak();
    liveApi.auth.getCheckinHistory().then(value => setCheckinHistory(value || [])).catch(() => {});
    const refresh = () => { void refreshStreak(); };
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, [refreshStreak]);
  // GET /auth/streak returns counters — streak_count, last_login_date,
  // cycle_week_number, consecutive_weeks, week_progress — so the count lives on
  // streak_count; the older field names stay as fallbacks.
  const currentStreak = streak?.streak_count ?? streak?.current_streak ?? streak?.days ?? streak?.count ?? 0;
  // Same tier gradient the dashboard streak card uses — the two cards now heat
  // up together as the user climbs tiers, from a single source of truth.

  const cycleDays = streak?.cycle_days ?? 7;
  const allowedMisses = streak?.allowed_misses ?? 2;

  // Local day key (YYYY-MM-DD). Built from local parts, not toISOString, so a
  // check-in just after midnight in Lagos still lands on the right day.
  const toDayKey = (value) => {
    const d = new Date(value);
    if (isNaN(d.getTime())) return null;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  // The check-in history endpoint is the source of truth for the calendar — the
  // streak record itself carries counters only.
  const todayStr = toDayKey(new Date());
  const checkinByDay = new Map();
  (checkinHistory || []).forEach((h) => {
    const key = toDayKey(h.checkin_date || h.date || h.checked_at);
    if (key) checkinByDay.set(key, h);
  });

  const monday = new Date();
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));

  const week = WEEK_DAYS.map((day, i) => {
    const d = new Date(monday);
    d.setDate(d.getDate() + i);
    const key = toDayKey(d);
    let status = 'pending';
    if (checkinByDay.has(key)) {
      status = checkinByDay.get(key).reclaimed ? 'reclaimed' : 'checked_in';
    } else {
      const authoritative = streak?.week_progress?.days?.[day];
      status = authoritative === 'checked' ? 'checked_in' : authoritative || (key < todayStr ? 'missed' : 'pending');
    }
    return { day, status, date: key };
  });

  const completedThisWeek = week.filter((d) => d.status === 'checked_in' || d.status === 'reclaimed').length;
  const missedThisWeek = week.filter((d) => d.status === 'missed').length;


  if (!streak) return <StreakSkeleton />;
  const tierGradient = getTierProgressGradient(hpBalance?.hp_earned_120day ?? 0);
  return <div className="space-y-5 animate-fade-in max-w-3xl mx-auto">
    <div><span className="hg-eyebrow">{msg('FE_STREAK_EYEBROW', 'Your consistency, rewarded')}</span><h1 className="font-heading font-extrabold text-2xl mt-1">{msg('FE_STREAK_PAGE_TITLE', 'Keep your fire going.')}</h1></div>
    <div className="grid gap-4 md:grid-cols-2">
      <StreakHero currentStreak={currentStreak} cycleDays={cycleDays} completedThisWeek={completedThisWeek} gradient={tierGradient} cycleWeek={streak.cycle_week_number || 1} />
      <OrderStreakCard summary={streak.order_streak} onRetry={refreshStreak} />
    </div>
    <StreakWeekCalendar week={week} completedThisWeek={completedThisWeek} cycleDays={cycleDays} missedThisWeek={missedThisWeek} allowedMisses={allowedMisses} />
    <section className="rounded-3xl tone-warn border border-warn/30 p-4 sm:p-5 flex items-start gap-3">
      <div className="rounded-2xl bg-warn/10 p-2.5"><RotateCcw className="w-5 h-5 text-warn" /></div>
      <div className="flex-1"><h2 className="font-bold text-sm">{msg('FE_STREAK_RECLAIM_TITLE', 'Missed a day? Reclaim it.')}</h2><p className="text-xs text-muted-foreground mt-1">{msg('FE_STREAK_RECLAIM_BODY', 'A food order or a wallet top-up of ₦1,000+ can reclaim an eligible missed login day.')}</p><div className="flex flex-wrap gap-2 mt-3"><Link to="/menu" className="rounded-full bg-gradient-cta text-white px-4 py-2 text-xs font-bold">{msg('FE_STREAK_ORDER_ACTION', 'Order now')}</Link><Link to="/wallet" className="rounded-full border border-warn/30 bg-card px-4 py-2 text-xs font-bold text-warn">{msg('FE_STREAK_TOPUP_ACTION', 'Top up wallet')}</Link></div></div>
    </section>
    <details className="rounded-2xl border border-border bg-card p-4 text-xs text-muted-foreground"><summary className="cursor-pointer font-bold text-foreground">{msg('FE_STREAK_RULES', 'How streaks work')}</summary><div className="space-y-2 mt-3"><p>{msg('FE_ORDER_STREAK_RULE', 'Have at least one paid food order delivered each week, Monday–Sunday in Nigeria time. A week without a qualifying delivery resets the streak.')}</p>{streak.order_streak?.repeat_after_week != null && <p>{msg('FE_ORDER_STREAK_REPEAT', 'After week {week}, the final configured HP reward repeats for each further consecutive week.', { week: streak.order_streak.repeat_after_week })}</p>}</div></details>
    <Link to="/rewards?tab=challenges" className="flex items-center justify-between rounded-2xl border border-border bg-card px-4 py-3 text-sm font-bold">{msg('FE_STREAK_REWARDS_LINK', 'Explore challenges on Rewards')}<ChevronRight className="w-4 h-4 text-primary" /></Link>
  </div>;
}
