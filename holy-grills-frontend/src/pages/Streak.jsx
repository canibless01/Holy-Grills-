import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, RotateCcw } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getTierProgressGradient } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import StreakSkeleton from '@/components/skeletons/StreakSkeleton';
import StreakHero from '@/components/streak/StreakHero';
import StreakWeekCalendar from '@/components/streak/StreakWeekCalendar';
import StreakMilestones from '@/components/streak/StreakMilestones';
import { triggerMascotCelebration } from '@/lib/mascots';

const WEEK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function Streak() {
  const { streak, refreshStreak, refreshHp, hpBalance } = useHolyGrill();
  const [myChallenges, setMyChallenges] = useState(null);
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

  // The current run started this many days back, so days before it never read
  // as "missed" — a brand-new member starts on a clean week.
  const cycleStart = new Date();
  cycleStart.setHours(0, 0, 0, 0);
  cycleStart.setDate(cycleStart.getDate() - Math.max(0, currentStreak - 1));
  const cycleStartStr = toDayKey(cycleStart);

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
    } else if (key >= cycleStartStr && key <= todayStr) {
      // Inside the current streak run — the streak counter confirms these days
      // were checked in, even when the history endpoint hasn't recorded them yet.
      status = 'checked_in';
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
        toast({ title: 'Already completed', description: 'You claimed this milestone already.' });
      } else if (res?.hp_awarded) {
        triggerMascotCelebration('thumbsup');
        toast({ title: '🎉 Milestone complete!', description: `+${res.hp_awarded} HP added.` });
      } else {
        toast({ title: 'Not yet!', description: 'Keep going — you haven\'t met the target yet.' });
      }
    } catch (e) {
      toast({ title: 'Could not complete', description: e.message, variant: 'destructive' });
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

  const badges = myChallenges?.badges || [];
  const availableChallenges = myChallenges?.challenges_available || [];
  const completedChallenges = myChallenges?.challenges_completed || [];

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <div>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Your Streak 🔥</h1>
        <p className="text-sm text-muted-foreground mt-1">Log in daily to keep your streak alive. Miss a day? Order or top up ₦1,000+ to reclaim it.</p>
      </div>

      <StreakHero
        currentStreak={currentStreak}
        cycleDays={cycleDays}
        completedThisWeek={completedThisWeek}
        gradient={tierGradient}
      />

      <StreakWeekCalendar
        week={week}
        completedThisWeek={completedThisWeek}
        cycleDays={cycleDays}
        missedThisWeek={missedThisWeek}
        allowedMisses={allowedMisses}
      />

      <StreakMilestones
        badges={badges}
        availableChallenges={availableChallenges}
        completedChallenges={completedChallenges}
        completing={completing}
        onComplete={handleCompleteChallenge}
        onSocialFollowClaimed={handleSocialFollowClaimed}
      />

      <div className="rounded-3xl bg-amber-50 border border-amber-200 p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-2xl bg-amber-100 flex items-center justify-center shrink-0">
            <RotateCcw className="w-5 h-5 text-amber-600" />
          </div>
          <div className="flex-1">
            <div className="font-bold text-sm text-foreground">Missed a day? Reclaim it.</div>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">Place an order or top up your wallet by ₦1,000+ and we'll restore that day automatically — your streak won't skip a beat.</p>
            <div className="flex gap-2 mt-3">
              <Link to="/menu" className="px-4 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold transition-all active:scale-95">Order now</Link>
              <Link to="/wallet" className="px-4 py-2 rounded-full bg-card border border-amber-200 text-amber-700 text-xs font-bold transition-all active:scale-95">Top up wallet</Link>
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