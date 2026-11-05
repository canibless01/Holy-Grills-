import { useEffect, useRef } from 'react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';

/**
 * Campus Ambassador link tracking.
 *
 * Mounted once near the app root. Two jobs:
 *
 *  1. When the URL carries ?ref=CODE (an ambassador's permanent tracking
 *     link), POST a click. Works for guests too — the anonymous id stored in
 *     localStorage keeps the trail until they sign up or log in.
 *  2. Once a session becomes authenticated, merge that anonymous click trail
 *     into the user's account exactly once, so existing customers who clicked
 *     while logged out still get a persistent 7-day ambassador attribution.
 *
 * The original referral flow is untouched: Register.tsx still reads ?ref= for
 * profiles.referred_by, and this component only feeds the separate ambassador
 * attribution tables. All failures are swallowed — tracking must never break
 * rendering, checkout or login.
 */
export default function AmbassadorClickTracker() {
  const { user } = useHolyGrill();
  const mergeDone = useRef<string | null>(null);

  // 1. Record the click whenever the page loads with a ref code.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const ref = (params.get('ref') || params.get('referral') || '').trim();
      if (!ref) return;
      void liveApi.ambassadors.trackClick(ref).catch(() => undefined);
    } catch {
      /* no-op: tracking is best-effort */
    }
  }, []);

  // 2. Adopt the anonymous trail after authentication, once per user/device.
  useEffect(() => {
    const userId = user?.id || user?.user_id;
    if (!userId) return;
    let anonId = '';
    try {
      anonId = localStorage.getItem('hg_amb_anonymous_id') || '';
    } catch {
      return;
    }
    if (!anonId) return;
    const dedupeKey = `${userId}:${anonId}`;
    if (mergeDone.current === dedupeKey) return;
    if (sessionStorage.getItem(`hg_amb_merged:${dedupeKey}`)) {
      mergeDone.current = dedupeKey;
      return;
    }
    mergeDone.current = dedupeKey;
    void liveApi.ambassadors
      .mergeVisitor(anonId)
      .then(() => sessionStorage.setItem(`hg_amb_merged:${dedupeKey}`, '1'))
      .catch(() => undefined);
  }, [user]);

  return null;
}
