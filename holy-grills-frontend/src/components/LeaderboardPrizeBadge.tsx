import { useState } from 'react';
import { rankMedal } from '@/lib/rewardUtils';

// Medal icon for a leaderboard rank, with a tap-to-open tooltip showing the
// rank's reward (X free sides + 1 exclusive spin). Rendered inside each row.
interface LeaderboardPrizeBadgeProps {
  rank: number;
  // Optional: without a prize row the badge still explains the medal.
  prize?: {
    free_sides?: number;
    free_side_count?: number;
    exclusive_spin?: boolean;
    includes_spin?: boolean;
    [key: string]: unknown;
  };
}

export default function LeaderboardPrizeBadge({ rank, prize }: LeaderboardPrizeBadgeProps) {
  const medal = rankMedal(rank);
  const [open, setOpen] = useState(false);
  if (!medal) return null;

  const freeSides = prize?.free_sides ?? prize?.free_side_count ?? null;
  const exclusiveSpin = prize?.exclusive_spin ?? prize?.includes_spin ?? true;

  return (
    <div className="relative" onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>
      <span className="text-base leading-none cursor-pointer select-none">{medal}</span>
      {open && (
        <div className="absolute right-0 top-7 z-40 w-52 rounded-2xl bg-white border border-border shadow-xl p-3 text-left">
          <div className="text-xs font-bold text-foreground mb-1">Rank #{rank} reward</div>
          <div className="text-xs text-foreground">
            {freeSides != null ? `${freeSides} free side${freeSides !== 1 ? 's' : ''}` : 'Free sides'}
            {exclusiveSpin ? ' + 1 exclusive spin' : ''}
          </div>
          <div className="text-[10px] text-muted-foreground mt-1">Tap the row to close.</div>
        </div>
      )}
    </div>
  );
}