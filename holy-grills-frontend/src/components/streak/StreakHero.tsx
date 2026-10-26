import { msg } from '@/lib/messages';
import { Flame } from 'lucide-react';
import CountUp from '@/components/CountUp';
import FlameMark from '@/components/FlameMark';
import { getStreakRewardHp } from '@/lib/featureConfig';

export default function StreakHero({ currentStreak, cycleDays, completedThisWeek, gradient, cycleWeek = 1, week = [] }) {
  const weeklyHp = getStreakRewardHp((cycleWeek - 1) * 7);
  const daysLeft = Math.max(0, cycleDays - completedThisWeek);

  return <section aria-label={msg('FE_LOGIN_STREAK_TITLE', 'Login streak')} className="relative overflow-hidden rounded-3xl p-5 sm:p-6 text-white shadow-card" style={{ background: gradient || 'linear-gradient(135deg, #E70E0E, #F2B84B)' }}>
    <FlameMark aria-hidden="true" className="absolute -right-4 -top-4 w-24 h-24 opacity-15" />
    <div className="relative">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center"><Flame className="w-4 h-4 text-white animate-flame-flicker" /></div>
          <h2 className="text-[10px] font-bold uppercase tracking-wide text-white/80">{msg('FE_LOGIN_STREAK_TITLE', 'Login streak')}</h2>
        </div>
        <span className="text-[10px] text-white/70 tabular-nums">{msg('FE_LOGIN_STREAK_WEEK_PROGRESS', '{done}/{total} this week', { done: completedThisWeek, total: cycleDays })}</span>
      </div>
      <div className="font-heading font-extrabold text-3xl text-white">
        <CountUp value={currentStreak} /><span className="ml-2 text-sm font-normal text-white/80">{msg('FE_LOGIN_STREAK_DAY_COUNT', 'day streak')}</span>
      </div>
      <ol aria-label={msg('FE_LOGIN_STREAK_DAILY_FLAMES', 'Daily check-in flames')} className="flex justify-between gap-1 mt-4">
        {week.map(day => {
          const checked = ['checked', 'checked_in', 'reclaimed'].includes(day.status);
          return <li key={day.day} aria-label={msg('FE_LOGIN_STREAK_DAY_STATUS', '{day}: {status}', { day: day.day, status: checked ? msg('FE_LOGIN_STREAK_CHECKED', 'checked in') : day.status === 'missed' ? msg('FE_LOGIN_STREAK_MISSED', 'missed') : msg('FE_LOGIN_STREAK_UPCOMING', 'not checked in') })} data-checked={checked ? 'true' : 'false'} className="flex flex-col items-center gap-1">
            <Flame aria-hidden="true" className={`w-5 h-5 ${checked ? 'text-white fill-white/20' : 'text-white/25'}`} />
            <span className="text-[9px] text-white/65">{day.day}</span>
          </li>;
        })}
      </ol>
      <div className="mt-4 flex items-center gap-2 rounded-2xl bg-white/10 px-3 py-2.5">
        <Flame className="w-4 h-4 text-amber-200 shrink-0" />
        <p className="text-xs text-white/90 leading-snug">{completedThisWeek >= cycleDays
          ? msg('FE_LOGIN_STREAK_WEEK_COMPLETE', 'Week complete — {hp} HP toward your pending balance.', { hp: weeklyHp })
          : msg('FE_LOGIN_STREAK_REWARD_PROGRESS', 'Complete this week for {hp} HP · {days} days to go', { hp: weeklyHp, days: daysLeft })}</p>
      </div>
    </div>
  </section>;
}
