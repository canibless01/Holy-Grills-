import { useState, useEffect } from 'react';
import { Timer } from 'lucide-react';

// Live elapsed timer for a kitchen order ticket. Ticks every second from
// received_at. Turns red + pulses when the elapsed time exceeds the kitchen's
// avg_prep_target_minutes setting (from /kitchen/settings).
export default function KitchenTimer({ receivedAt, targetMinutes }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!receivedAt) return;
    const calc = () => {
      const start = new Date(receivedAt).getTime();
      setElapsed(Number.isFinite(start) ? Math.max(0, Math.floor((Date.now() - start) / 1000)) : 0);
    };
    calc();
    const interval = setInterval(calc, 1000);
    return () => clearInterval(interval);
  }, [receivedAt]);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const display = mins >= 1440 ? `${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h`
    : mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}:${String(secs).padStart(2, '0')}`;
  const overTarget = targetMinutes != null && mins >= targetMinutes;

  return (
    <div className={`flex items-center gap-1 text-xs font-bold tabular-nums ${overTarget ? 'text-destructive' : 'text-muted-foreground'}`}>
      <Timer className={`w-3 h-3 ${overTarget ? 'animate-pulse' : ''}`} />
      <span className={overTarget ? 'animate-pulse' : ''}>{display}</span>
    </div>
  );
}
