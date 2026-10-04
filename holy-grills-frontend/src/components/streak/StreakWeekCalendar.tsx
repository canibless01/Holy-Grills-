import React from 'react';
import { Check, X, RotateCcw } from 'lucide-react';

const WEEK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function StreakWeekCalendar({ week, completedThisWeek, cycleDays, missedThisWeek, allowedMisses }) {
  const pct = Math.min(100, (completedThisWeek / cycleDays) * 100);

  return (
    <div className="rounded-3xl bg-card border border-border p-5 shadow-card">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">This Week</span>
        <span className="text-xs font-semibold text-foreground tabular-nums">{completedThisWeek}/{cycleDays} done · {missedThisWeek}/{allowedMisses} missed</span>
      </div>
      <div className="h-2.5 rounded-full bg-secondary mb-4 overflow-hidden">
        <div className="h-full rounded-full bg-gradient-cta transition-all duration-700 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {week.map((d, i) => (
          <div key={i} className="flex flex-col items-center gap-1.5">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold transition-all ${
              d.status === 'checked_in' ? 'bg-emerald-100 text-emerald-600 shadow-sm' :
              d.status === 'reclaimed' ? 'bg-amber-100 text-amber-600 shadow-sm' :
              d.status === 'missed' ? 'bg-red-50 text-red-400' : 'bg-muted text-muted-foreground/50'
            }`}>
              {d.status === 'checked_in' ? <Check className="w-4 h-4" /> :
               d.status === 'reclaimed' ? <RotateCcw className="w-4 h-4" /> :
               d.status === 'missed' ? <X className="w-3.5 h-3.5" /> : <span className="text-[10px]">·</span>}
            </div>
            <span className="text-[9px] text-muted-foreground font-semibold">{d.day}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 mt-4 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1"><Check className="w-3 h-3 text-emerald-500" /> Checked in</span>
        <span className="flex items-center gap-1"><RotateCcw className="w-3 h-3 text-amber-500" /> Reclaimed</span>
        <span className="flex items-center gap-1"><X className="w-3 h-3 text-red-400" /> Missed</span>
      </div>
    </div>
  );
}