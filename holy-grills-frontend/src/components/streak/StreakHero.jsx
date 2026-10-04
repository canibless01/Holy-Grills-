import React from 'react';
import { Flame } from 'lucide-react';
import CountUp from '@/components/CountUp';
import { getStreakRewardHp } from '@/lib/featureConfig';

export default function StreakHero({ currentStreak, cycleDays, completedThisWeek, gradient }) {
  const weeklyHp = getStreakRewardHp(currentStreak);
  const daysLeft = cycleDays - completedThisWeek;

  return (
    <>
      <div className="relative overflow-hidden rounded-3xl p-6 text-white shadow-glow" style={{ background: gradient || 'linear-gradient(135deg, #E70E0E, #F2B84B)' }}>
        <div className="absolute -right-6 -top-8 text-[7rem] opacity-10 select-none leading-none">🔥</div>
        <div className="relative">
          <div className="text-[10px] font-bold uppercase tracking-widest text-white/70">Login Streak</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-heading text-5xl font-extrabold tabular-nums leading-none"><CountUp value={currentStreak} /></span>
            <span className="text-sm font-medium text-white/70">day{currentStreak !== 1 ? 's' : ''}</span>
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-2xl bg-white/10 px-3 py-2.5 backdrop-blur-sm">
            <Flame className="w-4 h-4 text-amber-200 shrink-0" />
            <div className="text-xs text-white/90 leading-snug">
              {completedThisWeek >= cycleDays
                ? <span className="font-semibold">Week complete — {weeklyHp} HP heading to your pending balance.</span>
                : <span>Complete this week for <span className="font-bold text-white">{weeklyHp} HP</span> · {daysLeft} day{daysLeft !== 1 ? 's' : ''} to go</span>}
            </div>
          </div>
        </div>
      </div>

    </>
  );
}