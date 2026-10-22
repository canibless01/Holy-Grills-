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
      .then(value => { if (active) setRank(value?.rank_entry || (value?.rank ? value : null)); })
      .catch(() => { /* An unavailable rank is not a fabricated position. */ });
    refresh();
    window.addEventListener('focus', refresh);
    return () => { active = false; window.removeEventListener('focus', refresh); };
  }, [user?.id, user?.role, campusId, hpBalance?.active]);
  return rank;
}
