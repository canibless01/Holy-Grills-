import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, RotateCcw } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import type { MyChallengesEnvelope } from '@/types/challenges';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgressGradient } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import StreakSkeleton from '@/components/skeletons/StreakSkeleton';
import StreakHero from '@/components/streak/StreakHero';
import StreakWeekCalendar from '@/components/streak/StreakWeekCalendar';
import InstallPushBonuses from '@/components/challenges/InstallPushBonuses';
import StreakMilestones from '@/components/streak/StreakMilestones';
import { triggerMascotCelebration } from '@/lib/mascots';
import { msg } from '@/lib/messages';

const WEEK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function Streak() {
  const { streak, refreshStreak, refreshHp, hpBalance } = useHolyGrill();
  const [myChallenges, setMyChallenges] = useState<MyChallengesEnvelope | null>(null);
  const [checkinHistory, setCheckinHistory] = useState([]);
  const [completing, setCompleting] = useState(null);
  const loading = !streak;

  useEffect(() => {
    if (!streak) refreshStreak();
    Promise.allSettled([
      liveApi.auth.getCheckinHistory(),
      liveApi.challenges.my(),
    ]).then(([hist, ch]) => {
      if (hist.status === 'fulfilled') setCheckinHistory(hist.value || []);
      if (ch.status === 'fulfilled') setMyChallenges(ch.value);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // GET /auth/streak returns counters — streak_count, last_login_date,
  // cycle_week_number, consecutive_weeks, week_progress — so the count lives on
  // streak_count; the older field names stay as fallbacks.
  const currentStreak = streak?.streak_count ?? streak?.current_streak ?? streak?.days ?? streak?.count ?? 0;
  // Same tier gradient the dashboard streak card uses — the two cards now heat
  // up together as the user climbs tiers, from a single source of truth.
  const tierGradient = getTierProgressGradient(hpBalance?.hp_earned_120day ?? 0);
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

  const handleCompleteChallenge = async (ch) => {
    setCompleting(ch.id);
    try {
      const res = await liveApi.challenges.complete(ch.id);
      await refreshHp();
      const updated = await liveApi.challenges.my().catch(() => null);
      if (updated) setMyChallenges(updated);
      if (res?.already_completed) {
        toast({ title: msg('FE_STREAK_ALREADY_COMPLETED', 'Already completed'), description: msg('FE_STREAK_YOU_CLAIMED_THIS_MILESTONE_ALREADY', 'You claimed this milestone already.') });
      } else if (res?.hp_awarded) {
        triggerMascotCelebration('thumbsup');
        toast({ title: msg('FE_STREAK_MILESTONE_COMPLETE', '🎉 Milestone complete!'), description: msg('FE_STREAK_HP_HP_ADDED', '+{hp} HP added.', { hp: res.hp_awarded }) });
      } else {
        toast({ title: msg('FE_STREAK_NOT_YET', 'Not yet!'), description: msg('FE_STREAK_KEEP_GOING_YOU_HAVEN_T_MET_THE_TARGET', 'Keep going — you haven\'t met the target yet.') });
      }
    } catch (e) {
      toast({ title: msg('FE_STREAK_COULD_NOT_COMPLETE', 'Could not complete'), description: e.message, variant: 'destructive' });
    }
    setCompleting(null);
  };

  // After a successful social-follow claim (handled by the dedicated endpoint
  // inside SocialFollowChallenge), refresh HP + the challenge list — the same
  // post-success work handleCompleteChallenge does, minus the API call.
  const handleSocialFollowClaimed = async () => {
    await refreshHp();
    const updated = await liveApi.challenges.my().catch(() => null);
    if (updated) setMyChallenges(updated);
    triggerMascotCelebration('thumbsup');
  };

  if (loading) return <StreakSkeleton />;

  const availableChallenges = [...(myChallenges?.milestones_available || []), ...(myChallenges?.challenges_available || [])];
  const completedChallenges = [...(myChallenges?.milestones_completed || []), ...(myChallenges?.challenges_completed || [])];

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <div>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Your Streak 🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Log in daily to keep your streak alive. Miss a day? Order or top up ₦1,000+ to reclaim it.</p>
      </div>

      <h2 className="font-heading font-bold text-lg">{msg('FE_LOGIN_STREAK_TITLE', 'Login streak')}</h2>
      <StreakHero
        currentStreak={currentStreak}
        cycleDays={cycleDays}
        completedThisWeek={completedThisWeek}
        gradient={tierGradient}
      />

      <section id="ordering-streak" className="rounded-3xl border border-primary/20 bg-card p-5 space-y-3 scroll-mt-24">
        <h2 className="font-heading font-bold text-lg">{msg('FE_ORDER_STREAK_TITLE', 'Ordering streak')}</h2>
        {streak.order_streak ? <>
          <div className="flex items-baseline gap-2"><strong className="text-3xl text-primary">{streak.order_streak.streak_weeks}</strong><span>{msg('FE_ORDER_STREAK_WEEKS', 'consecutive weeks')}</span></div>
          <p className="text-sm text-muted-foreground">{msg('FE_ORDER_STREAK_RULE', 'Have at least one paid food order delivered each week, Monday–Sunday in Nigeria time. A week without a qualifying delivery resets the streak.')}</p>
          <p className="text-sm font-semibold">{streak.order_streak.counted_this_week ? msg('FE_ORDER_STREAK_COUNTED', 'This week is counted.') : msg('FE_ORDER_STREAK_WAITING', 'This week is waiting for a qualifying delivery.')}</p>
          <div className="flex flex-wrap gap-2">{streak.order_streak.rewards.map(reward => <div key={reward.weeks} className="rounded-xl bg-primary/5 border border-primary/15 px-3 py-2 text-sm"><span>{msg('FE_ORDER_STREAK_REWARD', 'Week {week}: {hp} HP', { week: reward.weeks, hp: reward.hp_awarded })}</span></div>)}</div>
          {streak.order_streak.repeat_after_week != null && <p className="text-xs text-muted-foreground">{msg('FE_ORDER_STREAK_REPEAT', 'After week {week}, the final configured HP reward repeats for each further consecutive week.', { week: streak.order_streak.repeat_after_week })}</p>}
          {!streak.order_streak.rewards.length && <p className="text-sm text-muted-foreground">{msg('FE_ORDER_STREAK_NO_REWARDS', 'No ordering-streak HP rewards are configured yet.')}</p>}
          <Link to="/menu" className="inline-flex rounded-full bg-gradient-cta text-white text-sm font-bold px-4 py-2">{msg('FE_ORDER_STREAK_MENU', 'Browse menu')}</Link>
        </> : <><p role="status" className="text-sm text-muted-foreground">{msg('FE_ORDER_STREAK_UNAVAILABLE', 'Your ordering streak could not be loaded.')}</p><button onClick={refreshStreak} className="text-primary text-sm font-bold">{msg('FE_LOOKUP_RETRY', 'Retry')}</button></>}
      </section>

      <StreakWeekCalendar
        week={week}
        completedThisWeek={completedThisWeek}
        cycleDays={cycleDays}
        missedThisWeek={missedThisWeek}
        allowedMisses={allowedMisses}
      />

      <InstallPushBonuses />

      <StreakMilestones
        availableChallenges={availableChallenges}
        completedChallenges={completedChallenges}
        completing={completing}
        onComplete={handleCompleteChallenge}
        onSocialFollowClaimed={handleSocialFollowClaimed}
      />

      <div className="rounded-3xl tone-warn border border-warn/40 p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-2xl tone-warn flex items-center justify-center shrink-0">
            <RotateCcw className="w-5 h-5 text-warn" />
          </div>
          <div className="flex-1">
            <div className="font-bold text-sm text-foreground">Missed a day? Reclaim it.</div>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">Place an order or top up your wallet by ₦1,000+ and we'll restore that day automatically — your streak won't skip a beat.</p>
            <div className="flex gap-2 mt-3">
              <Link to="/menu" className="px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold transition-all active:scale-95">Order now</Link>
              <Link to="/wallet" className="px-4 py-2 rounded-full bg-card border border-warn/40 text-warn text-xs font-bold transition-all active:scale-95">Top up wallet</Link>
            </div>
          </div>
        </div>
      </div>

      <Link to="/dashboard" className="flex items-center justify-center gap-1 text-sm text-muted-foreground pt-2 hover:text-foreground transition-colors">
        Back to dashboard <ChevronRight className="w-4 h-4" />
      </Link>
    </div>
  );
}