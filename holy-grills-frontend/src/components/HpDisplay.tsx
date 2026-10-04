import { Flame } from 'lucide-react';
import { getTierProgress } from '@/lib/hgUtils';
import FlameMark from '@/components/FlameMark';
import TierIcon from '@/components/TierIcon';

export default function HpDisplay({ hpBalance, compact = false }) {
  if (!hpBalance) return null;
  const tierInfo = getTierProgress(hpBalance.hp_earned_120day);

  if (compact) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-accent/10 border border-primary/20">
        <Flame className="w-4 h-4 text-primary" />
        <div className="flex items-baseline gap-1">
          <span className="font-bold text-lg text-foreground">{hpBalance.total_visible}</span>
          <span className="text-xs font-semibold text-primary uppercase">HP</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-gradient-dark p-5 text-white overflow-hidden relative">
      {/* Flame decoration */}
      <FlameMark className="absolute -right-4 -top-4 w-20 h-20 opacity-10" />

      <div className="flex items-center justify-between mb-4 relative">
        <div>
          <div className="text-xs text-accent font-bold uppercase tracking-wide">Holy Points</div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-4xl font-heading font-extrabold">{hpBalance.total_visible}</span>
            <span className="text-sm text-white/70 font-bold">HP</span>
          </div>
        </div>
        <div className="text-right">
          <TierIcon slug={tierInfo.current.slug} tier={tierInfo.current} className="w-8 h-8 text-3xl ml-auto" />
          <div className="text-sm font-bold mt-0.5">{tierInfo.current.name}</div>
          <div className="text-[10px] text-white/70">{tierInfo.current.earn_multiplier}x multiplier</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-xl bg-white/10 p-3">
          <div className="text-[10px] text-white/60 uppercase tracking-wide">Active</div>
          <div className="text-xl font-bold">{hpBalance.active}</div>
        </div>
        <div className="rounded-xl bg-white/10 p-3">
          <div className="text-[10px] text-white/60 uppercase tracking-wide">Pending</div>
          <div className="text-xl font-bold text-accent">{hpBalance.pending}</div>
        </div>
      </div>

      {/* Tier Progress */}
      {tierInfo.next && (
        <div>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-white/70 flex items-center gap-1.5">Progress to {tierInfo.next.name} <TierIcon slug={tierInfo.next.slug} tier={tierInfo.next} className="w-3.5 h-3.5 text-xs" /></span>
            <span className="font-bold text-accent">{tierInfo.remaining} HP to go</span>
          </div>
          <div className="h-2 rounded-full bg-black/30 overflow-hidden">
            <div className="h-full bg-gradient-cta rounded-full transition-all duration-500" style={{ width: `${tierInfo.progress}%` }} />
          </div>
        </div>
      )}

      {/* Pending unlock hint */}
      {hpBalance.pending > 0 && (
        <div className="mt-3 rounded-xl bg-primary/20 border border-primary/30 p-3 text-xs">
          <div className="flex items-center gap-1.5 text-accent font-semibold mb-1">
            <Flame className="w-3 h-3" />
            {hpBalance.pending} HP pending — order food to unlock
          </div>
          <p className="text-white/70">Every ₦1,000 food spend unlocks 30 HP from your pending pool.</p>
        </div>
      )}
    </div>
  );
}