import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';

export function useCurrentRank() {
  const { user, hpBalance } = useHolyGrill();
  const { campusId } = useCampus();
  const [rank, setRank] = useState(null);
  useEffect(() => {
    let active = true;
    setRank(null);
    if (!user?.id || !campusId || user.role !== 'student') return;
    const refresh = () => liveApi.leaderboard.getMyRank()
      .then(async value => {
        const monthly = value?.rank_entry || (value?.rank ? value : null);
        if (monthly) { if (active) setRank({ ...monthly, period_type: 'monthly' }); return; }
        const overall = await liveApi.leaderboard.getMyRank({ period_type: 'all_time' });
        const entry = overall?.rank_entry || (overall?.rank ? overall : null);
        if (active) setRank(entry ? { ...entry, period_type: 'all_time' } : { rank: null, unranked: true });
      })
      .catch(() => { /* An unavailable rank is not a fabricated position. */ });
    refresh();
    window.addEventListener('focus', refresh);
    return () => { active = false; window.removeEventListener('focus', refresh); };
  }, [user?.id, user?.role, campusId, hpBalance?.active, hpBalance?.pending, hpBalance?.hp_earned_120day]);
  return rank;
}
