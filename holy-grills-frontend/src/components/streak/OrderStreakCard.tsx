import { Check, ChevronRight, Flame, Utensils } from 'lucide-react';
import { Link } from 'react-router-dom';
import { msg } from '@/lib/messages';

export default function OrderStreakCard({ summary, onRetry }) {
  if (!summary) return <section id="ordering-streak" className="rounded-3xl tone-warn p-5 space-y-3"><h2 className="font-heading font-bold">{msg('FE_ORDER_STREAK_TITLE', 'Ordering streak')}</h2><p className="text-sm">{msg('FE_ORDER_STREAK_UNAVAILABLE', 'Your ordering streak could not be loaded.')}</p><button onClick={onRetry} className="font-bold text-sm underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button></section>;
  const next = summary.next_reward || summary.rewards.find(reward => reward.weeks > summary.streak_weeks);
  const goal = next?.weeks || summary.repeat_after_week || 1;
  return <section id="ordering-streak" className="relative overflow-hidden rounded-3xl bg-gradient-dark text-white p-5 sm:p-6 shadow-card scroll-mt-24">
    <div aria-hidden="true" className="absolute -right-12 -top-12 w-44 h-44 rounded-full bg-orange-400/15 blur-2xl" />
    <div className="relative space-y-4">
      <div className="flex items-center justify-between gap-2"><h2 className="text-[10px] uppercase font-bold tracking-widest text-white/70">{msg('FE_ORDER_STREAK_TITLE', 'Ordering streak')}</h2><Utensils className="w-5 h-5 text-amber-300" /></div>
      <div className="flex items-end justify-between gap-3">
        <div><span className="font-heading text-5xl font-extrabold tabular-nums">{summary.streak_weeks}</span><span className="ml-2 text-xs text-white/70">{msg('FE_ORDER_STREAK_WEEKS', 'consecutive weeks')}</span></div>
        <span className="flex items-center gap-1 rounded-full bg-white/10 px-2 py-1 text-[10px] font-bold text-amber-200">{summary.counted_this_week ? <Check className="w-3 h-3" /> : <Flame className="w-3 h-3" />}{summary.counted_this_week ? msg('FE_ORDER_STREAK_WEEK_DONE', 'Week secured') : msg('FE_ORDER_STREAK_WEEK_OPEN', 'Keep it going')}</span>
      </div>
      <div><div className="h-1.5 rounded-full bg-white/15 overflow-hidden"><div className="h-full rounded-full bg-gradient-cta" style={{ width: `${Math.min(100, summary.streak_weeks / goal * 100)}%` }} /></div><p className="mt-2 text-xs text-white/80">{next ? msg('FE_ORDER_STREAK_NEXT', 'Next: {hp} HP at week {week}', { hp: next.hp_awarded, week: next.weeks }) : msg('FE_ORDER_STREAK_WEEKLY_FOOD', 'One delivered food order. Every week.')}</p></div>
      <div className="flex gap-2 overflow-x-auto pb-1">{summary.rewards.map(reward => <div key={reward.weeks} className={`min-w-[72px] flex-1 rounded-2xl border px-2 py-2.5 text-center ${summary.streak_weeks >= reward.weeks ? 'border-amber-300/40 bg-amber-300/15' : 'border-white/15 bg-white/5'}`}><div className="text-[9px] text-white/65">{msg('FE_ORDER_STREAK_WEEK', 'Week {week}', { week: reward.weeks })}</div><div className="mt-0.5 text-sm font-extrabold text-amber-200">{reward.hp_awarded}<span className="ml-0.5 text-[9px]">HP</span></div></div>)}</div>
      <Link to="/menu" className="inline-flex items-center gap-1 text-xs font-bold text-amber-200">{msg('FE_ORDER_STREAK_MENU', 'Browse menu')}<ChevronRight className="w-3 h-3" /></Link>
    </div>
  </section>;
}
