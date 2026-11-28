import { useQuery } from '@tanstack/react-query';
import { getSessionGeneration } from '@/lib/apiClient';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';

export function useCurrentRank() {
  const { user, hpBalance } = useHolyGrill();
  const { campusId } = useCampus();
  const generation = getSessionGeneration();
  const eligible = !!user?.id && !!campusId && user.role === 'student';
  const { data } = useQuery({
    // Spending/unlocking pending HP does not by itself change earned ranking.
    // A changed earned total gets a new snapshot; Home and Dashboard share it.
    queryKey: ['current-rank', generation, user?.id, campusId, hpBalance?.hp_earned_120day],
    enabled: eligible,
    staleTime: 15000,
    gcTime: typeof window === 'undefined' ? Infinity : 5 * 60 * 1000,
    refetchOnWindowFocus: true,
    retry: (failures) => failures < 1 && generation === getSessionGeneration(),
    queryFn: async () => {
      if (generation !== getSessionGeneration()) throw new Error('Session changed');
      const value = await liveApi.leaderboard.getMyRank();
      const monthly = value?.rank_entry || (value?.rank ? value : null);
      if (monthly) return { ...monthly, period_type: 'monthly' };
      if (generation !== getSessionGeneration()) throw new Error('Session changed');
      const overall = await liveApi.leaderboard.getMyRank({ period_type: 'all_time' });
      const entry = overall?.rank_entry || (overall?.rank ? overall : null);
      return entry ? { ...entry, period_type: 'all_time' } : { rank: null, unranked: true };
    },
  });
  return eligible ? data ?? null : null;
}
